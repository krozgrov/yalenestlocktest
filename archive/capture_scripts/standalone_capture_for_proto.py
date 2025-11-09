#!/usr/bin/env python3
"""
Standalone capture script for proto refinement - avoids proto pool issues.

This captures Observe responses and uses blackboxprotobuf to generate typedefs
without importing proto_utils or reverse_engineering.
"""

import sys
import json
from pathlib import Path
from datetime import datetime, UTC
from dotenv import load_dotenv
import os
import requests
import re

try:
    import blackboxprotobuf as bbp
    BLACKBOX_AVAILABLE = True
except ImportError:
    BLACKBOX_AVAILABLE = False
    print("Error: blackboxprotobuf required. Install with: pip install blackboxprotobuf")
    sys.exit(1)

# Import only what we need, avoiding proto_utils
from auth import GetSessionWithAuth
from const import (
    ENDPOINT_OBSERVE,
    PRODUCTION_HOSTNAME,
    URL_PROTOBUF,
    API_TIMEOUT_SECONDS,
    USER_AGENT_STRING,
)

# Import v2_pb2 directly
sys.path.insert(0, str(Path(__file__).parent / "proto"))
from proto.nestlabs.gateway import v2_pb2


PROTO_SCALAR_TYPE_MAP = {
    "bool": "bool",
    "bytes": "bytes",
    "double": "double",
    "enum": "int32",
    "fixed32": "fixed32",
    "fixed64": "fixed64",
    "float": "float",
    "int": "int64",
    "int32": "int32",
    "int64": "int64",
    "sfixed32": "sfixed32",
    "sfixed64": "sfixed64",
    "sint": "sint64",
    "sint32": "sint32",
    "sint64": "sint64",
    "string": "string",
    "uint": "uint64",
    "uint32": "uint32",
    "uint64": "uint64",
    "varint": "uint64",
}

PROTO_RESERVED_WORDS = {
    "package", "syntax", "import", "option", "message", "enum",
    "repeated", "optional", "required", "map", "reserved", "returns", "rpc",
}


def _sanitize_identifier(name: str, prefix: str) -> str:
    candidate = re.sub(r"\W+", "_", name or "")
    if not candidate:
        candidate = prefix
    if candidate[0].isdigit():
        candidate = f"{prefix}_{candidate}"
    candidate_lower = candidate.lower()
    if candidate_lower in PROTO_RESERVED_WORDS:
        candidate = f"{candidate}_{prefix}"
    return candidate


def _snake_to_camel(name: str) -> str:
    parts = re.split(r"[_\s]+", name)
    return "".join(part.capitalize() for part in parts if part)


def _typedef_to_pseudo_proto(typedef: dict, message_name: str, depth: int = 0) -> str:
    indent = "  " * depth
    lines = [f"{indent}message {message_name} {{"]
    nested_sections = []
    
    try:
        field_items = sorted(typedef.items(), key=lambda item: int(item[0]) if str(item[0]).isdigit() else item[0])
    except Exception:
        field_items = typedef.items()
    
    for field_number, field_info in field_items:
        field_meta = field_info or {}
        field_name = _sanitize_identifier(field_meta.get("name") or f"field_{field_number}", "field")
        field_type = field_meta.get("type", "bytes")
        repeated = bool(field_meta.get("repeated"))
        
        if isinstance(field_type, (tuple, list)) and field_type:
            container = field_type
            field_type = container[0]
            if len(container) > 1 and not field_meta.get("message_typedef"):
                field_meta["message_typedef"] = container[1]
        
        if field_type in {"message", "group"}:
            nested_typedef = field_meta.get("message_typedef") or {}
            nested_name = field_meta.get("message_name") or f"{_snake_to_camel(field_name)}Message"
            nested_sections.append(_typedef_to_pseudo_proto(nested_typedef, nested_name, depth + 1))
            resolved_type = nested_name
        else:
            resolved_type = PROTO_SCALAR_TYPE_MAP.get(field_type, "bytes")
        
        label = "repeated " if repeated else ""
        lines.append(f"{indent}  {label}{resolved_type} {field_name} = {field_number};")
    
    if nested_sections:
        lines.append("")
        lines.extend(nested_sections)
    
    lines.append(f"{indent}}}")
    return "\n".join(lines)


def typedef_to_pseudo_proto(typedef: dict, root_name: str = "ObservedMessage") -> str:
    return _typedef_to_pseudo_proto(typedef, root_name)


def utc_timestamp(timespec: str = "seconds") -> str:
    return datetime.now(UTC).isoformat(timespec=timespec).replace("+00:00", "Z")


def _normalize_base(url: str | None) -> str | None:
    if not url:
        return None
    return url.rstrip("/")


def prepare_run_dir(base_dir: Path, traits: list[str]) -> Path:
    base_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    trait_suffix = "_".join(
        _sanitize_identifier(trait.split(".")[-1].lower(), "trait") for trait in traits
    ) or "observe"
    run_dir = base_dir / f"{timestamp}_{trait_suffix}"
    index = 1
    while run_dir.exists():
        run_dir = base_dir / f"{timestamp}_{trait_suffix}_{index}"
        index += 1
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Capture Observe responses for proto refinement"
    )
    parser.add_argument(
        "--traits",
        nargs="+",
        default=[
            "nest.trait.user.UserInfoTrait",
            "nest.trait.structure.StructureInfoTrait",
            "weave.trait.security.BoltLockTrait",
            "weave.trait.security.BoltLockSettingsTrait",
            "weave.trait.security.BoltLockCapabilitiesTrait",
            "weave.trait.security.PincodeInputTrait",
            "weave.trait.security.TamperTrait",
            "weave.trait.description.DeviceIdentityTrait",
            "weave.trait.power.BatteryPowerSourceTrait",
        ],
        help="Traits to capture",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Number of messages to capture",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("captures"),
        help="Output directory",
    )
    
    args = parser.parse_args()
    
    load_dotenv()
    
    print("="*80)
    print("STANDALONE CAPTURE FOR PROTO REFINEMENT")
    print("="*80)
    print()
    print(f"Traits: {', '.join(args.traits)}")
    print(f"Limit: {args.limit} messages")
    print()
    
    # Authenticate
    print("Authenticating...")
    session, access_token, _, transport_url = GetSessionWithAuth()
    print("✅ Authentication successful")
    print()
    
    # Build Observe request
    req = v2_pb2.ObserveRequest(version=2, subscribe=True)
    for trait_name in args.traits:
        filt = req.filter.add()
        filt.trait_type = trait_name
    payload = req.SerializeToString()
    
    # Determine transport URL
    default_base = URL_PROTOBUF.format(grpc_hostname=PRODUCTION_HOSTNAME["grpc_hostname"])
    base_candidates = []
    if transport_url:
        base_candidates.append(_normalize_base(transport_url))
    base_candidates.append(_normalize_base(default_base))
    
    # Send Observe request
    headers = {
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Content-Type": "application/x-protobuf",
        "User-Agent": USER_AGENT_STRING,
        "X-Accept-Response-Streaming": "true",
        "Accept": "application/x-protobuf",
        "referer": "https://home.nest.com/",
        "origin": "https://home.nest.com",
        "X-Accept-Content-Transfer-Encoding": "binary",
        "Authorization": "Basic " + access_token,
    }
    
    response = None
    for base in base_candidates:
        try:
            full_url = f"{base}{ENDPOINT_OBSERVE}"
            print(f"Sending Observe request to {full_url}...")
            response = session.post(
                full_url,
                headers=headers,
                data=payload,
                stream=True,
                timeout=(API_TIMEOUT_SECONDS, API_TIMEOUT_SECONDS),
            )
            response.raise_for_status()
            print("✅ Observe stream connected")
            break
        except Exception as e:
            print(f"❌ Failed: {e}")
            continue
    
    if not response:
        print("❌ Failed to connect to Observe stream")
        return 1
    
    # Prepare output directory
    run_dir = prepare_run_dir(args.output_dir, args.traits)
    print(f"Output directory: {run_dir}")
    print()
    
    # Process messages
    chunk_count = 0
    manifest = []
    
    print("Capturing and analyzing messages...")
    print()
    
    try:
        for chunk in response.iter_content(chunk_size=None):
            if not chunk or not chunk.strip():
                continue
            
            chunk_count += 1
            chunk_prefix = f"{chunk_count:05d}"
            
            # Save raw
            raw_path = run_dir / f"{chunk_prefix}.raw.bin"
            raw_path.write_bytes(chunk)
            
            entry = {
                "index": chunk_count,
                "timestamp": utc_timestamp(),
                "raw": raw_path.name,
                "size": len(chunk),
            }
            
            # Decode with blackboxprotobuf
            try:
                message_json, typedef = bbp.protobuf_to_json(chunk)
                
                blackbox_path = run_dir / f"{chunk_prefix}.blackbox.json"
                blackbox_path.write_text(json.dumps(message_json, indent=2))
                
                typedef_path = run_dir / f"{chunk_prefix}.typedef.json"
                typedef_path.write_text(json.dumps(typedef, indent=2, sort_keys=True, default=str))
                
                pseudo_proto = typedef_to_pseudo_proto(typedef, "ObservedMessage")
                pseudo_path = run_dir / f"{chunk_prefix}.pseudo.proto"
                pseudo_path.write_text(pseudo_proto)
                
                entry["blackbox"] = {
                    "message": blackbox_path.name,
                    "typedef": typedef_path.name,
                    "pseudo_proto": pseudo_path.name,
                }
                
                print(f"✅ Message {chunk_count}: {len(chunk)} bytes")
                print(f"   Top-level fields: {list(typedef.keys())}")
                
                # Show structure
                for field_num, field_info in list(typedef.items())[:3]:
                    field_type = field_info.get("type", "unknown")
                    if field_type == "message" and "message_typedef" in field_info:
                        nested = field_info["message_typedef"]
                        print(f"   Field {field_num}: message with {len(nested)} nested fields")
                    else:
                        print(f"   Field {field_num}: {field_type}")
                
            except Exception as e:
                entry["blackbox_error"] = str(e)
                print(f"⚠️  Message {chunk_count}: blackbox decode failed: {e}")
            
            manifest.append(entry)
            
            if chunk_count >= args.limit:
                break
    
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
    finally:
        response.close()
        session.close()
    
    # Save manifest
    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    
    # Save run config
    run_config = {
        "traits": args.traits,
        "limit": args.limit,
        "captured_chunks": chunk_count,
        "timestamp": utc_timestamp(),
    }
    config_path = run_dir / "run_config.json"
    config_path.write_text(json.dumps(run_config, indent=2))
    
    print()
    print("="*80)
    print("CAPTURE COMPLETE")
    print("="*80)
    print(f"Captured {chunk_count} message(s)")
    print(f"Location: {run_dir}")
    print()
    print("Files created:")
    for path in sorted(run_dir.iterdir()):
        print(f"  - {path.name}")
    print()
    print("Next steps:")
    print("1. Review pseudo.proto files to see actual API v2 structure")
    print("2. Compare with proto/nest/rpc.proto")
    print("3. Update proto files to match")
    print("4. Regenerate pb2.py files")
    print("5. Test parsing")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

