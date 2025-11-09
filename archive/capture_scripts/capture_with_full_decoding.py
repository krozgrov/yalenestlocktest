#!/usr/bin/env python3
"""
Capture messages and decode ALL traits in real-time during the stream.

This captures messages and immediately decodes all traits as they arrive,
avoiding the raw.bin file format issues.
"""

import sys
import json
import asyncio
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import os
import requests
from proto.nestlabs.gateway import v2_pb2
from protobuf_handler_enhanced import EnhancedProtobufHandler as NestProtobufHandler
from const import (
    API_TIMEOUT_SECONDS,
    USER_AGENT_STRING,
    ENDPOINT_OBSERVE,
    URL_PROTOBUF,
    PRODUCTION_HOSTNAME
)

# Import trait decoders
sys.path.insert(0, str(Path(__file__).parent / "proto"))

try:
    from proto.weave.trait import description_pb2
    from proto.weave.trait import power_pb2
    from proto.weave.trait import security_pb2
    from proto.nest.trait import structure_pb2
    from proto.nest.trait import user_pb2
    from google.protobuf.any_pb2 import Any
    PROTO_AVAILABLE = True
except ImportError as e:
    PROTO_AVAILABLE = False
    print(f"Warning: Some proto modules not available: {e}", file=sys.stderr)

load_dotenv()

ISSUE_TOKEN = os.environ.get("ISSUE_TOKEN")
COOKIES = os.environ.get("COOKIES")

if not ISSUE_TOKEN or not COOKIES:
    print("Error: ISSUE_TOKEN and COOKIES must be set in .env file")
    sys.exit(1)


def _normalize_base(url: str | None) -> str | None:
    if not url:
        return None
    return url.rstrip("/")


def _transport_candidates(session_base: str | None) -> list[str]:
    candidates = []
    normalized_session = _normalize_base(session_base)
    if normalized_session:
        candidates.append(normalized_session)
    default = _normalize_base(URL_PROTOBUF.format(grpc_hostname=PRODUCTION_HOSTNAME["grpc_hostname"]))
    if default and default not in candidates:
        candidates.append(default)
    return candidates


def _normalize_any_type(any_message: Any) -> Any:
    """Map legacy Nest type URLs onto googleapis prefix."""
    if not isinstance(any_message, Any):
        return any_message
    type_url = any_message.type_url or ""
    if type_url.startswith("type.nestlabs.com/"):
        normalized = Any()
        normalized.value = any_message.value
        normalized.type_url = type_url.replace("type.nestlabs.com/", "type.googleapis.com/", 1)
        return normalized
    return any_message


def decode_all_traits_from_handler(handler: NestProtobufHandler) -> Dict[str, Any]:
    """Extract all traits from handler's stream_body."""
    all_traits = {}
    
    if not PROTO_AVAILABLE:
        return all_traits
    
    try:
        stream_body = handler.stream_body
        
        for msg in stream_body.message:
            for get_op in msg.get:
                obj_id = get_op.object.id if get_op.object.id else None
                property_any = getattr(get_op.data, "property", None)
                
                if not property_any:
                    continue
                
                property_any = _normalize_any_type(property_any)
                type_url = property_any.type_url or ""
                
                if not type_url:
                    if hasattr(get_op, "data") and 7 in get_op.data:
                        type_url = "weave.trait.security.BoltLockTrait"
                    else:
                        continue
                
                trait_key = f"{obj_id}:{type_url}"
                trait_info = {"object_id": obj_id, "type_url": type_url, "decoded": False}
                
                try:
                    # DeviceIdentityTrait
                    if "DeviceIdentityTrait" in type_url:
                        trait = description_pb2.DeviceIdentityTrait()
                        property_any.Unpack(trait)
                        trait_info["decoded"] = True
                        trait_info["data"] = {
                            "serial_number": trait.serial_number if trait.serial_number else None,
                            "firmware_version": trait.fw_version if trait.fw_version else None,
                            "manufacturer": trait.manufacturer.value if trait.HasField("manufacturer") else None,
                            "model": trait.model_name.value if trait.HasField("model_name") else None,
                        }
                    
                    # BatteryPowerSourceTrait
                    elif "BatteryPowerSourceTrait" in type_url:
                        trait = power_pb2.BatteryPowerSourceTrait()
                        property_any.Unpack(trait)
                        trait_info["decoded"] = True
                        trait_info["data"] = {
                            "battery_level": trait.remaining.remainingPercent.value if trait.HasField("remaining") and trait.remaining.HasField("remainingPercent") else None,
                            "voltage": trait.assessedVoltage.value if trait.HasField("assessedVoltage") else None,
                            "condition": trait.condition,
                            "status": trait.status,
                            "replacement_indicator": trait.replacementIndicator,
                        }
                    
                    # BoltLockTrait
                    elif "BoltLockTrait" in type_url and "BoltLockSettings" not in type_url and "BoltLockCapabilities" not in type_url:
                        trait = security_pb2.BoltLockTrait()
                        property_any.Unpack(trait)
                        trait_info["decoded"] = True
                        trait_info["data"] = {
                            "locked_state": trait.lockedState,
                            "actuator_state": trait.actuatorState,
                            "originator": trait.boltLockActor.originator.resourceId if trait.HasField("boltLockActor") and trait.boltLockActor.HasField("originator") else None,
                        }
                    
                    # StructureInfoTrait
                    elif "StructureInfoTrait" in type_url:
                        trait = structure_pb2.StructureInfoTrait()
                        property_any.Unpack(trait)
                        trait_info["decoded"] = True
                        trait_info["data"] = {
                            "legacy_id": trait.legacy_id if trait.legacy_id else None,
                            "ssid": trait.ssid if trait.ssid else None,
                        }
                    
                    # UserInfoTrait
                    elif "UserInfoTrait" in type_url:
                        trait = user_pb2.UserInfoTrait()
                        property_any.Unpack(trait)
                        trait_info["decoded"] = True
                        trait_info["data"] = {"user_id": obj_id}
                
                except Exception as e:
                    trait_info["error"] = str(e)
                
                all_traits[trait_key] = trait_info
    
    except Exception:
        pass
    
    return all_traits


async def main():
    # HomeKit-relevant traits
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
    
    print("="*80)
    print("CAPTURING AND DECODING ALL TRAITS IN REAL-TIME")
    print("="*80)
    print()
    print("Traits:")
    for trait in trait_names:
        print(f"  - {trait}")
    print()
    
    # Prepare output
    output_dir = Path("captures")
    output_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    capture_dir = output_dir / f"{timestamp}_full_trait_decode"
    capture_dir.mkdir(exist_ok=True)
    
    print(f"Output directory: {capture_dir}")
    print()
    
    # Authenticate
    print("Authenticating...")
    headers = {
        'Sec-Fetch-Mode': 'cors',
        'X-Requested-With': 'XmlHttpRequest',
        'Referer': 'https://accounts.google.com/o/oauth2/iframe',
        'cookie': COOKIES,
        'User-Agent': USER_AGENT_STRING,
        'timeout': f"{API_TIMEOUT_SECONDS}",
    }
    response = requests.request("GET", ISSUE_TOKEN, headers=headers)
    google_access_token = response.json().get("access_token")
    session = requests.Session()
    
    nest_url = "https://nestauthproxyservice-pa.googleapis.com/v1/issue_jwt"
    nest_headers = {
        'Authorization': f'Bearer {google_access_token}',
        'User-Agent': USER_AGENT_STRING,
        'Referer': URL_PROTOBUF,
        'timeout': f"{API_TIMEOUT_SECONDS}"
    }
    nest_response = session.request("POST", nest_url, headers=nest_headers, json={
        "embed_google_oauth_access_token": "true",
        "expire_after": "3600s",
        "google_oauth_access_token": google_access_token,
        "policy_id": "authproxy-oauth-policy"
    })
    access_token = nest_response.json().get("jwt")
    
    session_url = "https://home.nest.com/session"
    session_headers = {
        'Authorization': f'Basic {access_token}',
        'User-Agent': USER_AGENT_STRING,
        'Referer': 'https://home.nest.com/',
        'timeout': f"{API_TIMEOUT_SECONDS}"
    }
    session_response = session.post(session_url, headers=session_headers)
    session_data = session_response.json()
    transport_url = session_data.get("urls", {}).get("transport_url")
    
    print("✅ Authentication successful")
    print()
    
    # Build Observe Request
    req = v2_pb2.ObserveRequest(version=2, subscribe=True)
    for trait_name in trait_names:
        filt = req.filter.add()
        filt.trait_type = trait_name
    payload_observe = req.SerializeToString()
    
    # Send Observe request
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
    for base_url in _transport_candidates(transport_url):
        target_url = f"{base_url}{ENDPOINT_OBSERVE}"
        try:
            print(f"Sending Observe request to {target_url}")
            response = session.post(target_url, headers=headers_observe, data=payload_observe, stream=True, timeout=(API_TIMEOUT_SECONDS, API_TIMEOUT_SECONDS))
            response.raise_for_status()
            observe_response = response
            break
        except Exception as err:
            print(f"Failed for {target_url}: {err}")
            continue
    
    if observe_response is None:
        print("❌ Failed to open Observe stream")
        return 1
    
    print("✅ Observe stream connected")
    print()
    
    # Process messages
    handler = NestProtobufHandler()
    chunk_count = 0
    limit = 5
    all_decoded_traits = {}
    
    print(f"Capturing and decoding up to {limit} messages...")
    print()
    
    try:
        import asyncio
        for chunk in observe_response.iter_content(chunk_size=None):
            if not chunk:
                continue
            
            # Process chunk manually (simulate handler's stream processing)
            # The handler processes varint-prefixed messages
            if handler.pending_length is None:
                handler.pending_length, offset = handler._decode_varint(chunk, 0)
                if handler.pending_length is None or offset >= len(chunk):
                    continue
                handler.buffer.extend(chunk[offset:])
            else:
                handler.buffer.extend(chunk)
            
            # Process complete messages
            while handler.pending_length and len(handler.buffer) >= handler.pending_length:
                message = handler.buffer[:handler.pending_length]
                handler.buffer = handler.buffer[handler.pending_length:]
                locks_data = await handler._process_message(message)
                handler.pending_length = None if len(handler.buffer) < 5 else handler._decode_varint(handler.buffer, 0)[0]
                
                if locks_data.get("yale") or locks_data.get("user_id") or locks_data.get("structure_id") or locks_data.get("all_traits"):
                    chunk_count += 1
                    print(f"✅ Message {chunk_count} processed")
                    
                    # Extract all traits from handler result
                    traits = locks_data.get("all_traits", {})
                    
                    if traits:
                        print(f"  Decoded {len(traits)} trait(s):")
                        for trait_key, trait_info in sorted(traits.items()):
                            type_url = trait_info["type_url"]
                            if trait_info.get("decoded"):
                                print(f"    ✅ {type_url}")
                                for key, value in trait_info.get("data", {}).items():
                                    if value is not None:
                                        print(f"       {key}: {value}")
                                        # Store for summary
                                        if type_url not in all_decoded_traits:
                                            all_decoded_traits[type_url] = []
                                        all_decoded_traits[type_url].append({key: value})
                            else:
                                print(f"    ⚠️  {type_url}: {trait_info.get('error', 'Not decoded')}")
                        print()
                    
                    # Save decoded data
                    decoded_file = capture_dir / f"{chunk_count:05d}.decoded.json"
                    with open(decoded_file, "w") as f:
                        json.dump(locks_data, f, indent=2, default=str)
                    
                    if chunk_count >= limit:
                        break
    
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    # Save summary
    metadata = {
        "traits": trait_names,
        "chunk_count": chunk_count,
        "timestamp": datetime.now().isoformat(),
        "decoded_traits": all_decoded_traits,
    }
    with open(capture_dir / "manifest.json", "w") as f:
        json.dump(metadata, f, indent=2, default=str)
    
    print()
    print("="*80)
    print("CAPTURE COMPLETE")
    print("="*80)
    print(f"Captured {chunk_count} message(s)")
    print(f"Location: {capture_dir}")
    print()
    
    if all_decoded_traits:
        print("Successfully decoded traits:")
        for trait_type, data_list in all_decoded_traits.items():
            print(f"  ✅ {trait_type}")
            for data in data_list:
                for key, value in data.items():
                    print(f"     {key}: {value}")
    else:
        print("⚠️  No traits decoded")
    
    session.close()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

