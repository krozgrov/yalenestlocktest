#!/usr/bin/env python3
"""
Compare blackboxprotobuf typedef with existing proto definitions.

This helps identify what's missing or different in the proto files.
"""

import json
import sys
import re
from pathlib import Path
from typing import Dict, Any, List, Set


def extract_proto_fields(proto_file: Path) -> Dict[str, Dict[str, Any]]:
    """Extract field definitions from a proto file."""
    if not proto_file.exists():
        return {}
    
    with open(proto_file, "r") as f:
        content = f.read()
    
    fields = {}
    
    # Extract message definitions
    message_pattern = r'message\s+(\w+)\s*\{([^}]+)\}'
    for match in re.finditer(message_pattern, content, re.DOTALL):
        message_name = match.group(1)
        message_body = match.group(2)
        
        # Extract fields from message
        # Pattern: [repeated] type name = number;
        field_pattern = r'(?:repeated\s+)?(\w+(?:\.\w+)*)\s+(\w+)\s*=\s*(\d+);'
        for field_match in re.finditer(field_pattern, message_body):
            field_type = field_match.group(1)
            field_name = field_match.group(2)
            field_number = field_match.group(3)
            
            if message_name not in fields:
                fields[message_name] = {}
            
            fields[message_name][field_number] = {
                "name": field_name,
                "type": field_type,
            }
    
    return fields


def load_typedef(typedef_file: Path) -> Dict[str, Any]:
    """Load typedef from JSON file."""
    with open(typedef_file, "r") as f:
        return json.load(f)


def compare_structures(typedef: Dict[str, Any], proto_fields: Dict[str, Dict[str, Any]], message_name: str = "StreamBody") -> Dict[str, Any]:
    """Compare typedef structure with proto fields."""
    comparison = {
        "message_name": message_name,
        "typedef_fields": set(typedef.keys()),
        "proto_fields": set(),
        "missing_in_proto": [],
        "extra_in_proto": [],
        "matches": [],
    }
    
    # Get proto fields for this message
    if message_name in proto_fields:
        comparison["proto_fields"] = set(proto_fields[message_name].keys())
        comparison["missing_in_proto"] = sorted(
            comparison["typedef_fields"] - comparison["proto_fields"],
            key=lambda x: int(x) if str(x).isdigit() else 999
        )
        comparison["extra_in_proto"] = sorted(
            comparison["proto_fields"] - comparison["typedef_fields"],
            key=int
        )
        comparison["matches"] = sorted(
            comparison["typedef_fields"] & comparison["proto_fields"],
            key=lambda x: int(x) if str(x).isdigit() else 999
        )
    else:
        comparison["missing_in_proto"] = list(comparison["typedef_fields"])
    
    return comparison


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Compare typedef with proto definitions"
    )
    parser.add_argument(
        "--capture-dir",
        type=Path,
        help="Capture directory with typedef.json files",
    )
    parser.add_argument(
        "--proto-file",
        type=Path,
        default=Path("proto/nest/rpc.proto"),
        help="Proto file to compare against",
    )
    
    args = parser.parse_args()
    
    # Find latest capture
    if args.capture_dir:
        capture_dir = args.capture_dir
    else:
        captures_dir = Path("captures")
        capture_dirs = sorted([d for d in captures_dir.iterdir() if d.is_dir()],
                            key=lambda x: x.stat().st_mtime, reverse=True)
        if not capture_dirs:
            print("Error: No captures found")
            return 1
        capture_dir = capture_dirs[0]
    
    print("="*80)
    print("COMPARING TYPEDEF WITH PROTO DEFINITIONS")
    print("="*80)
    print()
    print(f"Capture: {capture_dir.name}")
    print(f"Proto: {args.proto_file}")
    print()
    
    # Load proto fields
    proto_fields = extract_proto_fields(args.proto_file)
    print(f"Proto messages found: {list(proto_fields.keys())}")
    print()
    
    # Load and merge typedefs
    typedef_files = sorted(capture_dir.glob("*.typedef.json"))
    if not typedef_files:
        print("Error: No typedef.json files found")
        return 1
    
    print(f"Loading {len(typedef_files)} typedef file(s)...")
    
    merged_typedef = {}
    for typedef_file in typedef_files:
        typedef = load_typedef(typedef_file)
        # Merge
        for field_num, field_info in typedef.items():
            if field_num not in merged_typedef:
                merged_typedef[field_num] = field_info
            elif isinstance(field_info, dict) and isinstance(merged_typedef[field_num], dict):
                merged_typedef[field_num].update(field_info)
    
    print(f"Typedef fields: {list(merged_typedef.keys())}")
    print()
    
    # Compare StreamBody
    print("="*80)
    print("STREAMBODY COMPARISON")
    print("="*80)
    print()
    
    comparison = compare_structures(merged_typedef, proto_fields, "StreamBody")
    
    print(f"Typedef fields: {len(comparison['typedef_fields'])}")
    print(f"  {sorted(comparison['typedef_fields'], key=lambda x: int(x) if str(x).isdigit() else 999)}")
    print()
    
    print(f"Proto fields: {len(comparison['proto_fields'])}")
    if comparison['proto_fields']:
        print(f"  {sorted(comparison['proto_fields'], key=int)}")
    print()
    
    print(f"✅ Matches: {len(comparison['matches'])}")
    if comparison['matches']:
        print(f"  {comparison['matches']}")
    print()
    
    if comparison["missing_in_proto"]:
        print(f"⚠️  Missing in proto ({len(comparison['missing_in_proto'])}):")
        for field_num in comparison["missing_in_proto"]:
            field_info = merged_typedef.get(field_num, {})
            field_type = field_info.get("type", "unknown")
            field_name = field_info.get("name", f"field_{field_num}")
            print(f"  Field {field_num}: {field_name} ({field_type})")
            if field_type == "message" and "message_typedef" in field_info:
                nested = field_info["message_typedef"]
                print(f"    Nested message with {len(nested)} fields")
        print()
    
    if comparison["extra_in_proto"]:
        print(f"ℹ️  Extra in proto (not in typedef): {comparison['extra_in_proto']}")
        print()
    
    # Show nested structure
    print("="*80)
    print("NESTED MESSAGE STRUCTURE")
    print("="*80)
    print()
    
    for field_num, field_info in merged_typedef.items():
        if isinstance(field_info, dict) and field_info.get("type") == "message":
            nested_typedef = field_info.get("message_typedef", {})
            if nested_typedef:
                print(f"Field {field_num} (message) has {len(nested_typedef)} nested fields:")
                for nested_field_num in sorted(nested_typedef.keys(), 
                                              key=lambda x: int(x) if str(x).isdigit() else 999)[:10]:
                    nested_info = nested_typedef[nested_field_num]
                    nested_type = nested_info.get("type", "unknown")
                    nested_name = nested_info.get("name", f"field_{nested_field_num}")
                    print(f"  {nested_field_num}: {nested_name} ({nested_type})")
                if len(nested_typedef) > 10:
                    print(f"  ... and {len(nested_typedef) - 10} more")
                print()
    
    print("="*80)
    print("RECOMMENDATIONS")
    print("="*80)
    print()
    print("1. Review the missing fields above")
    print("2. Check if they should be added to StreamBody or nested messages")
    print("3. Update proto/nest/rpc.proto accordingly")
    print("4. Regenerate pb2.py files")
    print("5. Test parsing")
    print()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

