#!/usr/bin/env python3
"""
Capture Observe responses and analyze structure to refine proto files.

This script:
1. Captures raw Observe responses
2. Extracts protobuf messages (removes varint prefixes)
3. Uses blackboxprotobuf to decode structure
4. Compares with existing proto definitions
5. Identifies what needs to be updated
"""

import json
import sys
import asyncio
from pathlib import Path
from typing import Dict, Any
import subprocess

try:
    import blackboxprotobuf as bbp
    BLACKBOX_AVAILABLE = True
except ImportError:
    BLACKBOX_AVAILABLE = False
    print("Warning: blackboxprotobuf not available. Install with: pip install blackboxprotobuf")

from protobuf_handler import NestProtobufHandler


def extract_protobuf_messages(raw_data: bytes) -> list[bytes]:
    """Extract all protobuf messages from raw data (handles varint prefixes)."""
    handler = NestProtobufHandler()
    messages = []
    pos = 0
    
    while pos < len(raw_data):
        length, offset = handler._decode_varint(raw_data, pos)
        
        if length is None or length == 0:
            break
        
        if offset + length <= len(raw_data):
            message = raw_data[offset:offset + length]
            messages.append(message)
            pos = offset + length
        else:
            break
    
    return messages


def analyze_message_structure(message: bytes) -> Dict[str, Any]:
    """Analyze a protobuf message structure using blackboxprotobuf."""
    if not BLACKBOX_AVAILABLE:
        return {"error": "blackboxprotobuf not available"}
    
    try:
        message_json, typedef = bbp.protobuf_to_json(message)
        return {
            "success": True,
            "json": message_json,
            "typedef": typedef,
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


def compare_typedef_with_proto(typedef: Dict[str, Any], proto_file: Path) -> Dict[str, Any]:
    """Compare typedef structure with existing proto file."""
    if not proto_file.exists():
        return {"error": f"Proto file not found: {proto_file}"}
    
    # Read proto and extract field numbers
    with open(proto_file, "r") as f:
        proto_content = f.read()
    
    # Simple regex to find field definitions
    import re
    field_pattern = r'(?:repeated\s+)?\w+\s+\w+\s*=\s*(\d+);'
    proto_fields = set(re.findall(field_pattern, proto_content))
    typedef_fields = set(typedef.keys())
    
    missing = typedef_fields - proto_fields
    extra = proto_fields - typedef_fields
    
    return {
        "proto_fields": sorted(proto_fields, key=int),
        "typedef_fields": sorted(typedef_fields, key=lambda x: int(x) if str(x).isdigit() else 999),
        "missing_in_proto": sorted(missing, key=lambda x: int(x) if str(x).isdigit() else 999),
        "extra_in_proto": sorted(extra, key=int),
    }


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Capture and analyze Observe responses to refine proto files"
    )
    parser.add_argument(
        "--capture-file",
        type=Path,
        help="Raw capture file to analyze",
    )
    parser.add_argument(
        "--capture-dir",
        type=Path,
        help="Capture directory to analyze",
    )
    
    args = parser.parse_args()
    
    if not BLACKBOX_AVAILABLE:
        print("Error: blackboxprotobuf is required. Install with: pip install blackboxprotobuf")
        return 1
    
    print("="*80)
    print("ANALYZING MESSAGE STRUCTURE FOR PROTO REFINEMENT")
    print("="*80)
    print()
    
    # Find capture file
    if args.capture_file:
        capture_file = args.capture_file
    elif args.capture_dir:
        raw_files = sorted(args.capture_dir.glob("*.raw.bin"))
        if not raw_files:
            print(f"Error: No raw.bin files in {args.capture_dir}")
            return 1
        capture_file = raw_files[0]
    else:
        # Use latest capture
        captures_dir = Path("captures")
        capture_dirs = sorted([d for d in captures_dir.iterdir() if d.is_dir()],
                            key=lambda x: x.stat().st_mtime, reverse=True)
        if not capture_dirs:
            print("Error: No captures found")
            return 1
        raw_files = sorted(capture_dirs[0].glob("*.raw.bin"))
        if not raw_files:
            print("Error: No raw.bin files in latest capture")
            return 1
        capture_file = raw_files[0]
    
    print(f"Analyzing: {capture_file}")
    print()
    
    # Load raw data
    with open(capture_file, "rb") as f:
        raw_data = f.read()
    
    print(f"Raw data: {len(raw_data)} bytes")
    
    # Extract protobuf messages
    messages = extract_protobuf_messages(raw_data)
    print(f"Extracted {len(messages)} message(s)")
    print()
    
    # Analyze each message
    all_typedefs = {}
    successful = 0
    failed = 0
    
    for i, message in enumerate(messages, 1):
        print(f"Message {i}: {len(message)} bytes")
        
        result = analyze_message_structure(message)
        
        if result.get("success"):
            successful += 1
            typedef = result["typedef"]
            
            # Merge into all_typedefs
            for field_num, field_info in typedef.items():
                if field_num not in all_typedefs:
                    all_typedefs[field_num] = field_info
                elif isinstance(field_info, dict) and isinstance(all_typedefs[field_num], dict):
                    all_typedefs[field_num].update(field_info)
            
            print(f"  ✅ Decoded successfully")
            print(f"  Fields: {list(typedef.keys())}")
        else:
            failed += 1
            print(f"  ❌ Failed: {result.get('error', 'Unknown error')}")
        print()
    
    print(f"Summary: {successful} successful, {failed} failed")
    print()
    
    if not all_typedefs:
        print("❌ No typedef data extracted")
        return 1
    
    # Compare with existing proto
    print("="*80)
    print("COMPARING WITH EXISTING PROTO")
    print("="*80)
    print()
    
    rpc_proto = Path("proto/nest/rpc.proto")
    if rpc_proto.exists():
        comparison = compare_typedef_with_proto(all_typedefs, rpc_proto)
        
        print(f"Proto fields: {len(comparison['proto_fields'])}")
        print(f"  {comparison['proto_fields']}")
        print()
        print(f"Typedef fields: {len(comparison['typedef_fields'])}")
        print(f"  {comparison['typedef_fields']}")
        print()
        
        if comparison["missing_in_proto"]:
            print(f"⚠️  Missing in proto ({len(comparison['missing_in_proto'])}):")
            for field_num in comparison["missing_in_proto"]:
                field_info = all_typedefs.get(field_num, {})
                field_type = field_info.get("type", "unknown")
                print(f"  Field {field_num}: {field_type}")
            print()
        
        if comparison["extra_in_proto"]:
            print(f"ℹ️  Extra in proto (not in typedef): {comparison['extra_in_proto']}")
            print()
    else:
        print(f"⚠️  Proto file not found: {rpc_proto}")
        print()
    
    # Show typedef structure
    print("="*80)
    print("TYPEDEF STRUCTURE")
    print("="*80)
    print()
    print(json.dumps(all_typedefs, indent=2, default=str)[:2000])
    print()
    
    print("="*80)
    print("NEXT STEPS")
    print("="*80)
    print()
    print("1. Review the typedef structure above")
    print("2. Compare with proto/nest/rpc.proto")
    print("3. Update proto files to match the actual API v2 structure")
    print("4. Regenerate pb2.py files with: protoc --python_out=. proto/nest/rpc.proto")
    print("5. Test that StreamBody parsing works")
    print()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

