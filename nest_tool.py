#!/usr/bin/env python3
"""
Unified CLI tool for Nest Yale Lock testing and control.

Consolidates functionality from main.py, decode_traits.py, and related scripts.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
import requests
from proto.nestlabs.gateway import v2_pb2
from google.protobuf import any_pb2
from proto.weave.trait import security_pb2 as weave_security_pb2
import uuid

from auth import GetSessionWithAuth
from const import (
    API_TIMEOUT_SECONDS,
    USER_AGENT_STRING,
    ENDPOINT_OBSERVE,
    ENDPOINT_SENDCOMMAND,
    URL_PROTOBUF,
    PRODUCTION_HOSTNAME
)
from protobuf_handler import NestProtobufHandler
from protobuf_handler_enhanced import EnhancedProtobufHandler

load_dotenv()


def _normalize_base(url: str | None) -> str | None:
    """Normalize base URL."""
    if not url:
        return None
    return url.rstrip("/")


def _transport_candidates(session_base: str | None) -> list[str]:
    """Get transport URL candidates."""
    candidates = []
    normalized_session = _normalize_base(session_base)
    if normalized_session:
        candidates.append(normalized_session)
    default = _normalize_base(URL_PROTOBUF.format(grpc_hostname=PRODUCTION_HOSTNAME["grpc_hostname"]))
    if default and default not in candidates:
        candidates.append(default)
    return candidates


def _build_observe_payload(trait_names: Optional[list[str]] = None) -> bytes:
    """Build Observe request payload."""
    if trait_names is None:
        trait_names = [
            "nest.trait.user.UserInfoTrait",
            "nest.trait.structure.StructureInfoTrait",
            "weave.trait.security.BoltLockTrait",
            "weave.trait.security.BoltLockSettingsTrait",
            "weave.trait.security.BoltLockCapabilitiesTrait",
            "weave.trait.security.PincodeInputTrait",
            "weave.trait.security.TamperTrait",
            "weave.trait.description.DeviceIdentityTrait",
            "weave.trait.power.BatteryPowerSourceTrait",
        ]
    
    req = v2_pb2.ObserveRequest(version=2, subscribe=True)
    for trait_name in trait_names:
        filt = req.filter.add()
        filt.trait_type = trait_name
    return req.SerializeToString()


async def _observe_stream(session, access_token, transport_url, handler, max_messages: Optional[int] = None):
    """Observe stream and process with handler."""
    payload_observe = _build_observe_payload()
    
    headers_observe = {
        'Accept-Encoding': 'gzip, deflate, br, zstd',
        'Content-Type': 'application/x-protobuf',
        'User-Agent': USER_AGENT_STRING,
        'X-Accept-Response-Streaming': 'true',
        'Accept': 'application/x-protobuf',
        'referer': 'https://home.nest.com/',
        'origin': 'https://home.nest.com',
        'X-Accept-Content-Transfer-Encoding': 'binary',
        'Authorization': 'Basic ' + access_token
    }
    
    observe_response = None
    observe_base = None
    
    for base_url in _transport_candidates(transport_url):
        target_url = f"{base_url}{ENDPOINT_OBSERVE}"
        try:
            print(f"[nest_tool] Connecting to {target_url}...", file=sys.stderr)
            response = session.post(
                target_url,
                headers=headers_observe,
                data=payload_observe,
                stream=True,
                timeout=(API_TIMEOUT_SECONDS, API_TIMEOUT_SECONDS)
            )
            response.raise_for_status()
            observe_response = response
            observe_base = base_url
            break
        except requests.HTTPError as err:
            status = err.response.status_code if err.response else "unknown"
            print(f"[nest_tool] Failed for {target_url} (status {status}): {err}", file=sys.stderr)
        except Exception as err:
            print(f"[nest_tool] Error for {target_url}: {err}", file=sys.stderr)
    
    if observe_response is None:
        raise SystemExit("Failed to open Observe stream against all transport endpoints.")
    
    locks_data = {}
    message_count = 0
    
    try:
        for chunk in observe_response.iter_content(chunk_size=None):
            if chunk:
                new_data = await handler._process_message(chunk)
                if isinstance(new_data, dict):
                    locks_data.update(new_data)
                message_count += 1
                
                # Check if we have enough data
                user_id = locks_data.get("user_id") or locks_data.get("user_id")
                structure_id = locks_data.get("structure_id")
                if user_id and structure_id and max_messages is None:
                    # Got initial snapshot, can break if not subscribing
                    break
                
                if max_messages and message_count >= max_messages:
                    break
    finally:
        observe_response.close()
    
    return locks_data, observe_base


def _send_lock_command(session, access_token, device_id, user_id, structure_id, action: str, observe_base: Optional[str], transport_url: str, dry_run: bool = False):
    """Send lock/unlock command."""
    if action == "unlock":
        state = weave_security_pb2.BoltLockTrait.BOLT_STATE_RETRACTED
    elif action == "lock":
        state = weave_security_pb2.BoltLockTrait.BOLT_STATE_EXTENDED
    else:
        raise ValueError(f"Unsupported action: {action}")
    
    request = weave_security_pb2.BoltLockTrait.BoltLockChangeRequest()
    request.state = state
    request.boltLockActor.method = weave_security_pb2.BoltLockTrait.BOLT_LOCK_ACTOR_METHOD_REMOTE_USER_EXPLICIT
    request.boltLockActor.originator.resourceId = str(user_id)
    
    command = {
        "traitLabel": "bolt_lock",
        "command": {
            "type_url": "type.nestlabs.com/weave.trait.security.BoltLockTrait.BoltLockChangeRequest",
            "value": request.SerializeToString(),
        }
    }
    
    request_id = str(uuid.uuid4())
    headers = {
        "Authorization": f"Basic {access_token}",
        "Content-Type": "application/x-protobuf",
        "User-Agent": USER_AGENT_STRING,
        "X-Accept-Content-Transfer-Encoding": "binary",
        "X-Accept-Response-Streaming": "true",
        "request-id": request_id,
    }
    
    if structure_id:
        headers["X-Nest-Structure-Id"] = structure_id
    
    cmd_any = any_pb2.Any()
    cmd_any.type_url = command["command"]["type_url"]
    cmd_any.value = command["command"]["value"] if isinstance(command["command"]["value"], bytes) else command["command"]["value"].SerializeToString()
    
    from proto.nestlabs.gateway import v1_pb2
    resource_command = v1_pb2.ResourceCommand()
    resource_command.command.CopyFrom(cmd_any)
    resource_command.traitLabel = command["traitLabel"]
    
    request_pb = v1_pb2.ResourceCommandRequest()
    request_pb.resourceCommands.extend([resource_command])
    request_pb.resourceRequest.resourceId = device_id
    request_pb.resourceRequest.requestId = request_id
    encoded_data = request_pb.SerializeToString()
    
    if dry_run:
        print("Dry-run enabled; skipping command dispatch.", file=sys.stderr)
        print(f"Command payload (base64):", file=sys.stderr)
        import base64
        print(base64.b64encode(command["command"]["value"]).decode(), file=sys.stderr)
        return None
    
    command_base_candidates = []
    if observe_base:
        command_base_candidates.append(observe_base)
    command_base_candidates.extend(
        base for base in _transport_candidates(transport_url)
        if base not in command_base_candidates
    )
    
    for base_url in command_base_candidates:
        api_url = f"{base_url}{ENDPOINT_SENDCOMMAND}"
        try:
            print(f"[nest_tool] Sending {action} command to {api_url}...", file=sys.stderr)
            command_response = session.post(api_url, headers=headers, data=encoded_data, timeout=API_TIMEOUT_SECONDS)
            if command_response.status_code != 200:
                print(f"[nest_tool] Response body: {command_response.text}", file=sys.stderr)
                command_response.raise_for_status()
            
            response_message = v1_pb2.ResourceCommandResponseFromAPI()
            response_message.ParseFromString(command_response.content)
            return response_message
        except Exception as err:
            print(f"[nest_tool] Command attempt failed for {api_url}: {err}", file=sys.stderr)
            if base_url == command_base_candidates[-1]:
                raise
    
    raise RuntimeError("Command failed for all transport endpoints.")


def cmd_lock(args):
    """Lock control command."""
    session, access_token, user_id, transport_url = GetSessionWithAuth()
    
    try:
        handler = NestProtobufHandler()
        locks_data, observe_base = asyncio.run(_observe_stream(session, access_token, transport_url, handler))
        
        locks = locks_data.get("yale", {})
        device_id = None
        
        if args.device_id:
            lock_info = locks.get(args.device_id)
            if not lock_info:
                available = ", ".join(locks.keys()) or "none"
                raise SystemExit(f"Requested device_id '{args.device_id}' not found. Available locks: {available}")
            device_id = lock_info.get("device_id") or args.device_id
        else:
            for lock_id, lock_info in locks.items():
                if lock_info.get("device_id"):
                    device_id = lock_info["device_id"]
                    break
        
        if not device_id:
            raise SystemExit("No Yale lock device_id discovered; nothing to control.")
        
        if args.action == "status":
            lock_info = locks.get(device_id, {})
            output = {
                "device_id": device_id,
                "bolt_locked": lock_info.get("bolt_locked"),
                "bolt_moving": lock_info.get("bolt_moving"),
                "actuator_state": lock_info.get("actuator_state"),
                "user_id": locks_data.get("user_id"),
                "structure_id": locks_data.get("structure_id"),
            }
            print(json.dumps(output, indent=2))
            return
        
        # Send command
        response = _send_lock_command(
            session, access_token, device_id,
            locks_data.get("user_id") or user_id,
            locks_data.get("structure_id"),
            args.action, observe_base, transport_url, args.dry_run
        )
        
        if response:
            print("Command sent successfully.", file=sys.stderr)
            print(json.dumps({
                "status": "success",
                "device_id": device_id,
                "action": args.action
            }, indent=2))
    finally:
        session.close()


def cmd_decode(args):
    """Decode traits command."""
    session, access_token, user_id, transport_url = GetSessionWithAuth()
    
    try:
        handler = EnhancedProtobufHandler()
        locks_data, _ = asyncio.run(_observe_stream(session, access_token, transport_url, handler, max_messages=args.limit))
        
        if args.format == "json":
            print(json.dumps(locks_data, indent=2))
        elif args.format == "pretty":
            _print_pretty_traits(locks_data)
        else:  # table
            _print_table_traits(locks_data)
    finally:
        session.close()


def _print_pretty_traits(locks_data):
    """Print traits in a pretty format."""
    print("=" * 80)
    print("DECODED TRAITS")
    print("=" * 80)
    print()
    
    locks = locks_data.get("yale", {})
    if locks:
        print("🔒 Lock Data:")
        for device_id, lock_info in locks.items():
            print(f"  Device: {device_id}")
            print(f"    Locked: {lock_info.get('bolt_locked')}")
            print(f"    Moving: {lock_info.get('bolt_moving')}")
        print()
    
    user_id = locks_data.get("user_id")
    if user_id:
        print(f"👤 User ID: {user_id}")
        print()
    
    structure_id = locks_data.get("structure_id")
    if structure_id:
        print(f"🏠 Structure ID: {structure_id}")
        print()
    
    all_traits = locks_data.get("all_traits", {})
    if all_traits:
        print(f"📊 Decoded Traits ({len(all_traits)}):")
        print()
        
        for trait_key, trait_info in sorted(all_traits.items()):
            obj_id, type_url = trait_key.split(":", 1) if ":" in trait_key else (None, trait_key)
            decoded = trait_info.get("decoded", False)
            data = trait_info.get("data", {})
            
            trait_name = type_url.split(".")[-1] if "." in type_url else type_url
            status = "✅" if decoded else "⚠️"
            
            print(f"  {status} {trait_name}")
            if obj_id:
                print(f"      Object: {obj_id}")
            if decoded and data:
                print(f"      Data:")
                for key, value in data.items():
                    print(f"        {key}: {value}")
            print()


def _print_table_traits(locks_data):
    """Print traits in a table format."""
    try:
        from rich.console import Console
        from rich.table import Table
        from rich import box
        
        console = Console()
        
        # Lock summary
        locks = locks_data.get("yale", {})
        if locks:
            table = Table(title="🔒 Locks", box=box.ROUNDED)
            table.add_column("Device ID", style="cyan")
            table.add_column("Locked", style="green")
            table.add_column("Moving", style="yellow")
            
            for device_id, lock_info in locks.items():
                table.add_row(
                    device_id,
                    str(lock_info.get("bolt_locked", "N/A")),
                    str(lock_info.get("bolt_moving", "N/A"))
                )
            console.print(table)
            console.print()
        
        # Traits table
        all_traits = locks_data.get("all_traits", {})
        if all_traits:
            table = Table(title="📊 Decoded Traits", box=box.ROUNDED)
            table.add_column("Trait", style="cyan")
            table.add_column("Object ID", style="magenta")
            table.add_column("Status", style="green")
            table.add_column("Data", style="yellow")
            
            for trait_key, trait_info in sorted(all_traits.items()):
                obj_id, type_url = trait_key.split(":", 1) if ":" in trait_key else (None, trait_key)
                decoded = trait_info.get("decoded", False)
                data = trait_info.get("data", {})
                
                trait_name = type_url.split(".")[-1] if "." in type_url else type_url
                status = "✅ Decoded" if decoded else "⚠️  Not decoded"
                data_str = json.dumps(data, indent=2) if data else "N/A"
                
                table.add_row(
                    trait_name,
                    obj_id or "N/A",
                    status,
                    data_str[:100] + "..." if len(data_str) > 100 else data_str
                )
            console.print(table)
    except ImportError:
        # Fallback to pretty format if rich not available
        _print_pretty_traits(locks_data)


def main():
    parser = argparse.ArgumentParser(
        description="Unified CLI tool for Nest Yale Lock testing and control",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Check lock status
  python nest_tool.py lock --action status
  
  # Lock the device
  python nest_tool.py lock --action lock
  
  # Decode all traits (JSON)
  python nest_tool.py decode --format json
  
  # Decode all traits (pretty)
  python nest_tool.py decode --format pretty
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Lock command
    lock_parser = subparsers.add_parser("lock", help="Control lock (status/lock/unlock)")
    lock_parser.add_argument(
        "--action",
        choices=["status", "lock", "unlock"],
        default="status",
        help="Action to perform (default: status)"
    )
    lock_parser.add_argument(
        "--device-id",
        help="Lock device ID to control (defaults to first discovered)"
    )
    lock_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview command without sending"
    )
    
    # Decode command
    decode_parser = subparsers.add_parser("decode", help="Decode all traits from stream")
    decode_parser.add_argument(
        "--format",
        choices=["json", "pretty", "table"],
        default="pretty",
        help="Output format (default: pretty)"
    )
    decode_parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of messages to process"
    )
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    try:
        if args.command == "lock":
            cmd_lock(args)
        elif args.command == "decode":
            cmd_decode(args)
        else:
            parser.print_help()
            return 1
    except KeyboardInterrupt:
        print("\nInterrupted by user.", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        if args.debug if hasattr(args, 'debug') else False:
            traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

