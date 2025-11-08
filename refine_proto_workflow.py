#!/usr/bin/env python3
"""
Complete workflow to refine proto files from blackboxprotobuf output.

1. Capture fresh Observe responses with all traits
2. Extract typedefs from blackboxprotobuf
3. Compare with existing proto definitions
4. Identify missing/incomplete fields
5. Generate updated proto files
6. Compile to pb2.py
7. Test parsing
"""

import json
import sys
import subprocess
from pathlib import Path
from typing import Dict, Any, List
import re

# Import reverse_engineering to capture data
from reverse_engineering import capture_observe_stream


def extract_varint_prefixed_message(raw_data: bytes) -> bytes:
    """Extract protobuf message from varint-prefixed gRPC-web format."""
    if not raw_data:
        return b""
    
    # Decode varint length
    pos = 0
    value = 0
    shift = 0
    max_bytes = 10
    
    while pos < len(raw_data) and pos < max_bytes and shift < 64:
        byte = raw_data[pos]
        value |= (byte & 0x7F) << shift
        pos += 1
        shift += 7
        if not (byte & 0x80):
            if value > 0 and pos + value <= len(raw_data):
                return raw_data[pos:pos + value]
            break
    
    # If no varint found, assume whole thing is the message
    return raw_data


def load_and_merge_typedefs(capture_dir: Path) -> Dict[str, Any]:
    """Load and merge typedefs from a capture directory."""
    typedef_files = sorted(capture_dir.glob("*.typedef.json"))
    
    if not typedef_files:
        return {}
    
    merged = {}
    for typedef_file in typedef_files:
        try:
            with open(typedef_file, "r") as f:
                typedef = json.load(f)
                # Merge, preferring more complete definitions
                for field_num, field_info in typedef.items():
                    if field_num not in merged:
                        merged[field_num] = field_info
                    elif isinstance(field_info, dict) and isinstance(merged[field_num], dict):
                        # Merge nested typedefs
                        if "message_typedef" in field_info and "message_typedef" in merged[field_num]:
                            # Recursively merge nested typedefs
                            nested_merged = merged[field_num]["message_typedef"].copy()
                            for nested_field, nested_info in field_info["message_typedef"].items():
                                if nested_field not in nested_merged:
                                    nested_merged[nested_field] = nested_info
                                elif isinstance(nested_info, dict):
                                    nested_merged[nested_field].update(nested_info)
                            merged[field_num]["message_typedef"] = nested_merged
                        else:
                            merged[field_num].update(field_info)
        except Exception as e:
            print(f"Warning: Failed to load {typedef_file}: {e}")
    
    return merged


def compare_with_existing_proto(typedef: Dict[str, Any], proto_file: Path) -> Dict[str, Any]:
    """Compare typedef with existing proto file to find missing fields."""
    if not proto_file.exists():
        return {"error": f"Proto file not found: {proto_file}"}
    
    # Read proto file
    with open(proto_file, "r") as f:
        proto_content = f.read()
    
    # Extract field numbers from proto
    proto_fields = {}
    # Match patterns like "repeated NestMessage message = 1;"
    field_pattern = r'(?:repeated\s+)?\w+\s+\w+\s*=\s*(\d+);'
    for match in re.finditer(field_pattern, proto_content):
        field_num = match.group(1)
        proto_fields[field_num] = True
    
    # Find missing fields
    missing = {}
    for field_num, field_info in typedef.items():
        if field_num not in proto_fields:
            missing[field_num] = field_info
    
    return {
        "proto_fields": list(proto_fields.keys()),
        "typedef_fields": list(typedef.keys()),
        "missing_fields": missing,
    }


def generate_proto_updates(typedef: Dict[str, Any], message_name: str = "StreamBody") -> str:
    """Generate proto field definitions from typedef."""
    lines = []
    
    # Sort by field number
    try:
        items = sorted(typedef.items(), key=lambda x: int(x[0]) if str(x[0]).isdigit() else 999)
    except:
        items = list(typedef.items())
    
    for field_num, field_info in items:
        if not isinstance(field_info, dict):
            continue
        
        field_name = field_info.get("name") or f"field_{field_num}"
        field_type = field_info.get("type", "bytes")
        repeated = field_info.get("repeated", False)
        
        # Map types
        type_map = {
            "int": "int64",
            "int32": "int32",
            "int64": "int64",
            "uint": "uint64",
            "uint32": "uint32",
            "uint64": "uint64",
            "bool": "bool",
            "string": "string",
            "bytes": "bytes",
            "float": "float",
            "double": "double",
        }
        
        if field_type == "message" and "message_typedef" in field_info:
            # Nested message - use existing message type if we can identify it
            # For now, use a generic name
            nested_name = f"{message_name}Field{field_num}"
            resolved_type = nested_name
            # TODO: Generate nested message definition
        else:
            resolved_type = type_map.get(field_type, "bytes")
        
        label = "repeated " if repeated else ""
        lines.append(f"  {label}{resolved_type} {field_name} = {field_num};")
    
    return "\n".join(lines)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Refine proto files from blackboxprotobuf output"
    )
    parser.add_argument(
        "--capture",
        action="store_true",
        help="Capture fresh Observe responses first",
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
        "--capture-dir",
        type=Path,
        help="Use existing capture directory instead of capturing",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of messages to capture",
    )
    
    args = parser.parse_args()
    
    print("="*80)
    print("PROTO REFINEMENT WORKFLOW")
    print("="*80)
    print()
    
    # Step 1: Capture data if requested
    if args.capture:
        print("Step 1: Capturing Observe responses...")
        print(f"  Traits: {', '.join(args.traits)}")
        print(f"  Limit: {args.limit} messages")
        print()
        
        try:
            capture_dir, chunk_count = capture_observe_stream(
                traits=args.traits,
                output_dir=Path("captures"),
                limit=args.limit,
                capture_blackbox=True,
                capture_parsed=False,
                echo_blackbox=False,
                echo_parsed=False,
            )
            print(f"✅ Captured {chunk_count} messages to {capture_dir}")
            print()
        except Exception as e:
            print(f"❌ Capture failed: {e}")
            return 1
    elif args.capture_dir:
        capture_dir = args.capture_dir
        print(f"Using existing capture: {capture_dir}")
        print()
    else:
        # Use latest capture
        captures_dir = Path("captures")
        capture_dirs = sorted([d for d in captures_dir.iterdir() if d.is_dir()],
                            key=lambda x: x.stat().st_mtime, reverse=True)
        if not capture_dirs:
            print("Error: No captures found. Use --capture to create one.")
            return 1
        capture_dir = capture_dirs[0]
        print(f"Using latest capture: {capture_dir}")
        print()
    
    # Step 2: Load typedefs
    print("Step 2: Loading typedefs from blackboxprotobuf output...")
    typedef = load_and_merge_typedefs(capture_dir)
    
    if not typedef:
        print("❌ No typedef data found. Make sure capture includes blackbox output.")
        return 1
    
    print(f"✅ Loaded typedef with {len(typedef)} top-level fields")
    print()
    
    # Step 3: Compare with existing proto
    print("Step 3: Comparing with existing proto files...")
    rpc_proto = Path("proto/nest/rpc.proto")
    
    if rpc_proto.exists():
        comparison = compare_with_existing_proto(typedef, rpc_proto)
        print(f"  Proto fields: {len(comparison['proto_fields'])}")
        print(f"  Typedef fields: {len(comparison['typedef_fields'])}")
        print(f"  Missing fields: {len(comparison.get('missing_fields', {}))}")
        
        if comparison.get("missing_fields"):
            print("\n  Missing fields:")
            for field_num, field_info in comparison["missing_fields"].items():
                field_type = field_info.get("type", "unknown")
                print(f"    Field {field_num}: {field_type}")
        print()
    else:
        print(f"⚠️  Proto file not found: {rpc_proto}")
        print()
    
    # Step 4: Show structure
    print("Step 4: Typedef structure:")
    print(f"  Top-level fields: {list(typedef.keys())}")
    
    # Show nested structure
    for field_num, field_info in typedef.items():
        if isinstance(field_info, dict) and "message_typedef" in field_info:
            nested = field_info["message_typedef"]
            print(f"  Field {field_num} (message) has {len(nested)} nested fields")
            for nested_field in sorted(nested.keys(), key=lambda x: int(x) if str(x).isdigit() else 999)[:5]:
                nested_info = nested[nested_field]
                nested_type = nested_info.get("type", "unknown")
                print(f"    {nested_field}: {nested_type}")
            if len(nested) > 5:
                print(f"    ... and {len(nested) - 5} more")
    print()
    
    # Step 5: Generate suggested updates
    print("Step 5: Suggested proto updates:")
    print("="*80)
    print("Review the typedef structure above and manually update:")
    print("  - proto/nest/rpc.proto")
    print("  - Check for missing fields in StreamBody, NestMessage, TraitGetProperty, etc.")
    print()
    print("The typedef shows the actual structure from the API v2 responses.")
    print("Compare this with the existing proto definitions to identify gaps.")
    print("="*80)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

