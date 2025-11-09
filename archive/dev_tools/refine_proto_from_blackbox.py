#!/usr/bin/env python3
"""
Refine proto files based on blackboxprotobuf typedef output.

This script:
1. Loads typedef.json files from captures
2. Compares with existing proto definitions
3. Identifies missing fields
4. Updates proto files with missing fields
5. Regenerates pb2.py files
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any, List, Set
import subprocess

# Add proto to path
sys.path.insert(0, str(Path(__file__).parent / "proto"))


def load_typedef(capture_dir: Path) -> Dict[str, Any]:
    """Load typedef from a capture directory."""
    typedef_files = sorted(capture_dir.glob("*.typedef.json"))
    
    if not typedef_files:
        return {}
    
    # Merge all typedefs (they should be similar)
    merged = {}
    for typedef_file in typedef_files:
        try:
            with open(typedef_file, "r") as f:
                typedef = json.load(f)
                # Merge fields
                for field_num, field_info in typedef.items():
                    if field_num not in merged:
                        merged[field_num] = field_info
                    else:
                        # Prefer more complete field info
                        if isinstance(field_info, dict) and isinstance(merged[field_num], dict):
                            merged[field_num].update(field_info)
        except Exception as e:
            print(f"Warning: Failed to load {typedef_file}: {e}")
    
    return merged


def typedef_to_proto_fields(typedef: Dict[str, Any], message_name: str = "StreamBody") -> List[str]:
    """Convert typedef to proto field definitions."""
    fields = []
    
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
        
        # Map blackboxprotobuf types to proto types
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
            # Nested message - we'll need to handle this separately
            nested_name = f"{message_name}Field{field_num}"
            resolved_type = nested_name
        else:
            resolved_type = type_map.get(field_type, "bytes")
        
        label = "repeated " if repeated else ""
        fields.append(f"  {label}{resolved_type} {field_name} = {field_num};")
    
    return fields


def analyze_streambody_typedef(typedef: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze StreamBody typedef structure."""
    analysis = {
        "fields": {},
        "nested_messages": {},
        "missing_in_current_proto": [],
    }
    
    # Current StreamBody fields from rpc.proto
    current_fields = {
        "1": "message",  # repeated NestMessage
        "2": "status",   # Status
        "15": "noop",    # repeated bytes
    }
    
    for field_num, field_info in typedef.items():
        if not isinstance(field_info, dict):
            continue
        
        field_name = field_info.get("name") or f"field_{field_num}"
        field_type = field_info.get("type", "bytes")
        
        analysis["fields"][field_num] = {
            "name": field_name,
            "type": field_type,
            "repeated": field_info.get("repeated", False),
        }
        
        # Check if field exists in current proto
        if field_num not in current_fields:
            analysis["missing_in_current_proto"].append({
                "field_number": field_num,
                "name": field_name,
                "type": field_type,
                "info": field_info,
            })
        
        # Check for nested messages
        if field_type == "message" and "message_typedef" in field_info:
            nested_typedef = field_info["message_typedef"]
            analysis["nested_messages"][field_num] = {
                "name": field_name,
                "typedef": nested_typedef,
            }
    
    return analysis


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Refine proto files from blackboxprotobuf typedefs"
    )
    parser.add_argument(
        "--capture-dir",
        type=Path,
        help="Specific capture directory to analyze",
    )
    parser.add_argument(
        "--captures-dir",
        type=Path,
        default=Path("captures"),
        help="Directory containing captures",
    )
    parser.add_argument(
        "--update-proto",
        action="store_true",
        help="Actually update the proto files (default is just analysis)",
    )
    
    args = parser.parse_args()
    
    # Find capture directories
    if args.capture_dir:
        capture_dirs = [args.capture_dir]
    else:
        capture_dirs = sorted([d for d in args.captures_dir.iterdir() if d.is_dir()],
                            key=lambda x: x.stat().st_mtime, reverse=True)
    
    if not capture_dirs:
        print("Error: No capture directories found")
        return 1
    
    print("="*80)
    print("REFINING PROTO FILES FROM BLACKBOXPROTOBUF OUTPUT")
    print("="*80)
    print()
    
    # Load typedefs from captures
    all_typedefs = {}
    for capture_dir in capture_dirs[:3]:  # Use latest 3
        print(f"Loading typedefs from: {capture_dir.name}")
        typedef = load_typedef(capture_dir)
        if typedef:
            # Merge
            for field_num, field_info in typedef.items():
                if field_num not in all_typedefs:
                    all_typedefs[field_num] = field_info
                else:
                    # Prefer more complete info
                    if isinstance(field_info, dict) and isinstance(all_typedefs[field_num], dict):
                        all_typedefs[field_num].update(field_info)
            print(f"  Loaded {len(typedef)} fields")
    
    if not all_typedefs:
        print("Error: No typedef data found")
        return 1
    
    print(f"\nTotal unique fields found: {len(all_typedefs)}")
    print()
    
    # Analyze StreamBody structure
    analysis = analyze_streambody_typedef(all_typedefs)
    
    print("StreamBody Analysis:")
    print(f"  Fields found: {len(analysis['fields'])}")
    print(f"  Nested messages: {len(analysis['nested_messages'])}")
    print(f"  Missing in current proto: {len(analysis['missing_in_current_proto'])}")
    print()
    
    if analysis["missing_in_current_proto"]:
        print("Missing Fields:")
        for missing in analysis["missing_in_current_proto"]:
            print(f"  Field {missing['field_number']}: {missing['name']} ({missing['type']})")
        print()
    
    # Show all fields
    print("All Fields Found:")
    for field_num in sorted(analysis["fields"].keys(), key=lambda x: int(x) if str(x).isdigit() else 999):
        field = analysis["fields"][field_num]
        print(f"  {field_num}: {field['name']} ({field['type']})" + 
              (" [repeated]" if field["repeated"] else ""))
    print()
    
    # Show nested messages
    if analysis["nested_messages"]:
        print("Nested Messages:")
        for field_num, nested in analysis["nested_messages"].items():
            print(f"  Field {field_num}: {nested['name']}")
            nested_typedef = nested["typedef"]
            if isinstance(nested_typedef, dict):
                print(f"    Fields: {len(nested_typedef)}")
                for nested_field_num in sorted(nested_typedef.keys(), 
                                             key=lambda x: int(x) if str(x).isdigit() else 999)[:5]:
                    print(f"      {nested_field_num}: ...")
                if len(nested_typedef) > 5:
                    print(f"      ... and {len(nested_typedef) - 5} more")
        print()
    
    # If update requested, show what would be updated
    if args.update_proto:
        print("="*80)
        print("UPDATING PROTO FILES")
        print("="*80)
        print()
        print("⚠️  Proto file update not yet implemented")
        print("   This would require:")
        print("   1. Parsing existing proto files")
        print("   2. Adding missing fields")
        print("   3. Handling nested messages")
        print("   4. Regenerating pb2.py files")
        print()
        print("For now, manually review the analysis above and update:")
        print("  - proto/nest/rpc.proto (StreamBody message)")
        print("  - proto/nest/rpc.proto (NestMessage, TraitGetProperty, etc.)")
        print()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

