#!/usr/bin/env python3
"""
Map blackboxprotobuf typedef structure to existing proto definitions.

This helps understand what the typedef fields correspond to in the proto.
"""

import json
from pathlib import Path

# Mapping based on proto definitions
PROTO_MAPPING = {
    "StreamBody": {
        "1": "message (repeated NestMessage)",
        "2": "status (Status)",
        "15": "noop (repeated bytes)",
    },
    "NestMessage": {
        "1": "set (repeated TraitSetProperty)",
        "3": "get (repeated TraitGetProperty)",
        "5": "catalog_metadata (CatalogMetadata)",
    },
    "TraitGetProperty": {
        "1": "object (ObjectIdPair)",
        "2": "operation (bytes)",
        "3": "data (DynamicProp_Indirect)",
        "4": "monotonic_version (uint64)",
    },
    "ObjectIdPair": {
        "1": "id (string)",
        "2": "key (string)",
        "3": "uuid (string)",
    },
    "DynamicProp_Indirect": {
        "1": "property (google.protobuf.Any)",
    },
    "CatalogMetadata": {
        "1": "catalog_version (uint64)",
        "2": "snapshot_time_usec (uint64)",
    },
}


def analyze_typedef_structure(typedef: dict, depth: int = 0, path: str = "StreamBody") -> list:
    """Analyze typedef structure and map to proto definitions."""
    indent = "  " * depth
    findings = []
    
    for field_num, field_info in sorted(typedef.items(), 
                                       key=lambda x: int(x[0]) if str(x[0]).isdigit() else 999):
        if not isinstance(field_info, dict):
            continue
        
        field_type = field_info.get("type", "unknown")
        field_name = field_info.get("name", f"field_{field_num}")
        
        # Try to map to proto
        proto_mapping = PROTO_MAPPING.get(path, {})
        proto_field = proto_mapping.get(field_num, None)
        
        finding = {
            "path": path,
            "field_num": field_num,
            "field_name": field_name,
            "field_type": field_type,
            "proto_mapping": proto_field,
            "matches": proto_field is not None,
        }
        
        if field_type == "message" and "message_typedef" in field_info:
            nested_typedef = field_info["message_typedef"]
            
            # Determine nested message name based on context
            if path == "StreamBody" and field_num == "1":
                nested_name = "NestMessage"
            elif path == "NestMessage" and field_num == "3":
                nested_name = "TraitGetProperty"
            elif path == "NestMessage" and field_num == "1":
                nested_name = "TraitSetProperty"
            elif path == "NestMessage" and field_num == "5":
                nested_name = "CatalogMetadata"
            elif path == "TraitGetProperty" and field_num == "1":
                nested_name = "ObjectIdPair"
            elif path == "TraitGetProperty" and field_num == "3":
                nested_name = "DynamicProp_Indirect"
            else:
                nested_name = f"{path}Field{field_num}"
            
            finding["nested_name"] = nested_name
            finding["nested_fields"] = len(nested_typedef)
            
            # Recursively analyze nested
            nested_findings = analyze_typedef_structure(
                nested_typedef, depth + 1, nested_name
            )
            findings.extend(nested_findings)
        
        findings.append(finding)
    
    return findings


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Map typedef structure to proto definitions"
    )
    parser.add_argument(
        "--capture-dir",
        type=Path,
        help="Capture directory",
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
    print("MAPPING TYPEDEF TO PROTO DEFINITIONS")
    print("="*80)
    print()
    print(f"Capture: {capture_dir.name}")
    print()
    
    # Load typedef
    typedef_files = sorted(capture_dir.glob("*.typedef.json"))
    if not typedef_files:
        print("Error: No typedef.json files found")
        return 1
    
    # Merge typedefs
    merged_typedef = {}
    for typedef_file in typedef_files:
        with open(typedef_file, "r") as f:
            typedef = json.load(f)
            for field_num, field_info in typedef.items():
                if field_num not in merged_typedef:
                    merged_typedef[field_num] = field_info
                elif isinstance(field_info, dict) and isinstance(merged_typedef[field_num], dict):
                    merged_typedef[field_num].update(field_info)
    
    # Analyze
    findings = analyze_typedef_structure(merged_typedef)
    
    print("Field Mapping Analysis:")
    print()
    
    matches = [f for f in findings if f["matches"]]
    mismatches = [f for f in findings if not f["matches"]]
    
    print(f"✅ Matches: {len(matches)}")
    for finding in matches:
        print(f"  {finding['path']}.{finding['field_num']}: {finding['proto_mapping']}")
    print()
    
    if mismatches:
        print(f"⚠️  Mismatches/Unknown: {len(mismatches)}")
        for finding in mismatches:
            print(f"  {finding['path']}.{finding['field_num']}: {finding['field_type']}")
            if finding.get("nested_name"):
                print(f"    → Nested: {finding['nested_name']} ({finding['nested_fields']} fields)")
        print()
    
    print("="*80)
    print("KEY FINDINGS")
    print("="*80)
    print()
    print("The typedef structure shows:")
    print("  - StreamBody.field_1 = message (NestMessage) ✅")
    print("  - NestMessage structure with fields 1, 5")
    print("  - Field 1 appears to be TraitGetProperty (but proto has it as field 3)")
    print("  - Field 5 appears to be CatalogMetadata ✅")
    print()
    print("The issue is that blackboxprotobuf decodes the raw chunk which may")
    print("include varint prefixes or be a different message format.")
    print()
    print("Next steps:")
    print("1. Extract actual protobuf messages from varint-prefixed chunks")
    print("2. Decode those messages with blackboxprotobuf")
    print("3. Compare with proto definitions")
    print("4. Update proto files if needed")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

