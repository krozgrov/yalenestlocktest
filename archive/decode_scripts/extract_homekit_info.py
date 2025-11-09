#!/usr/bin/env python3
"""
Extract HomeKit-relevant information from decoded protobuf messages.

Searches for:
- Serial numbers
- Battery information
- Firmware/software versions
- Last contact timestamps
- Device capabilities
- Model information
- Any other HomeKit-relevant attributes
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any, Set
from collections import defaultdict


def extract_homekit_fields(blackbox_data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract all HomeKit-relevant fields from decoded data."""
    homekit_info = {
        "serial_numbers": [],
        "battery_info": [],
        "firmware_versions": [],
        "software_versions": [],
        "last_contact": [],
        "device_capabilities": [],
        "model_info": [],
        "manufacturer": [],
        "other_fields": [],
    }
    
    # Keywords to search for
    keyword_map = {
        "serial": "serial_numbers",
        "battery": "battery_info",
        "firmware": "firmware_versions",
        "software": "software_versions",
        "version": "software_versions",
        "contact": "last_contact",
        "timestamp": "last_contact",
        "time": "last_contact",
        "last": "last_contact",
        "model": "model_info",
        "manufacturer": "manufacturer",
        "capability": "device_capabilities",
        "state": "other_fields",
        "status": "other_fields",
        "level": "other_fields",
        "charge": "battery_info",
        "power": "battery_info",
    }
    
    def search_fields(obj: Any, path: str = "", depth: int = 0):
        if depth > 20:
            return
        
        if isinstance(obj, dict):
            for key, value in obj.items():
                key_str = str(key).lower()
                value_str = str(value).lower() if isinstance(value, (str, int, float)) else ""
                
                # Check for keywords
                for keyword, category in keyword_map.items():
                    if keyword in key_str or (isinstance(value, str) and keyword in value_str):
                        field_info = {
                            "path": path,
                            "key": key,
                            "value": value,
                            "full_path": f"{path}.{key}" if path else str(key),
                        }
                        
                        # Categorize
                        if category in homekit_info:
                            homekit_info[category].append(field_info)
                        else:
                            homekit_info["other_fields"].append(field_info)
                
                # Also check for numeric values that might be timestamps
                if isinstance(value, (int, str)) and key_str in ["timestamp", "time", "last", "contact"]:
                    try:
                        val = int(value) if isinstance(value, str) else value
                        if val > 1000000000:  # Likely a timestamp (Unix epoch)
                            homekit_info["last_contact"].append({
                                "path": path,
                                "key": key,
                                "value": val,
                                "full_path": f"{path}.{key}" if path else str(key),
                            })
                    except:
                        pass
                
                # Recursively search
                search_fields(value, f"{path}.{key}" if path else str(key), depth + 1)
        
        elif isinstance(obj, list):
            for idx, item in enumerate(obj):
                search_fields(item, f"{path}[{idx}]" if path else f"[{idx}]", depth + 1)
    
    search_fields(blackbox_data)
    return homekit_info


def extract_device_metadata(blackbox_data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract device metadata from message structure."""
    metadata = {
        "device_id": None,
        "device_type": None,
        "serial_number": None,
        "model": None,
        "manufacturer": None,
        "capabilities": [],
        "interfaces": [],
        "traits": [],
    }
    
    def find_device_info(obj: Any, depth: int = 0):
        if depth > 15:
            return
        
        if isinstance(obj, dict):
            # Look for device ID
            if "1" in obj and isinstance(obj["1"], str):
                device_id = obj["1"]
                if device_id.startswith("DEVICE_"):
                    metadata["device_id"] = device_id
                    metadata["serial_number"] = device_id.replace("DEVICE_", "")
                
                # Get resource type
                if "2" in obj:
                    resource_type = obj["2"]
                    metadata["device_type"] = resource_type
                    
                    # Extract model/manufacturer from resource type
                    if "yale" in resource_type.lower():
                        metadata["manufacturer"] = "Yale"
                    if "linus" in resource_type.lower():
                        metadata["model"] = "Linus Lock"
                
                # Get traits
                if "4" in obj:
                    trait_list = obj["4"] if isinstance(obj["4"], list) else [obj["4"]]
                    for trait in trait_list:
                        if isinstance(trait, dict) and "2" in trait:
                            metadata["traits"].append(trait["2"])
                
                # Get interfaces
                if "7" in obj:
                    iface_list = obj["7"] if isinstance(obj["7"], list) else [obj["7"]]
                    for iface in iface_list:
                        if isinstance(iface, dict) and "2" in iface:
                            metadata["interfaces"].append(iface["2"])
            
            # Recursively search
            for value in obj.values():
                find_device_info(value, depth + 1)
        
        elif isinstance(obj, list):
            for item in obj:
                find_device_info(item, depth + 1)
    
    find_device_info(blackbox_data)
    return metadata


def analyze_captures(capture_dirs: List[Path]) -> Dict[str, Any]:
    """Analyze all captures for HomeKit-relevant information."""
    all_homekit_info = defaultdict(list)
    all_metadata = []
    
    for capture_dir in capture_dirs:
        for blackbox_file in sorted(capture_dir.glob("*.blackbox.json")):
            try:
                with open(blackbox_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                # Extract HomeKit fields
                homekit_info = extract_homekit_fields(data)
                for category, fields in homekit_info.items():
                    if fields:
                        all_homekit_info[category].extend(fields)
                
                # Extract device metadata
                metadata = extract_device_metadata(data)
                if metadata["device_id"]:
                    all_metadata.append({
                        "file": blackbox_file.name,
                        **metadata,
                    })
            
            except Exception as e:
                print(f"Warning: Could not process {blackbox_file}: {e}", file=sys.stderr)
    
    return {
        "homekit_fields": dict(all_homekit_info),
        "device_metadata": all_metadata,
    }


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Extract HomeKit-relevant information from protobuf messages"
    )
    parser.add_argument(
        "--captures-dir",
        type=Path,
        default=Path("captures"),
        help="Directory containing capture files",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output JSON file for results",
    )
    
    args = parser.parse_args()
    
    if not args.captures_dir.exists():
        print(f"Error: Captures directory does not exist: {args.captures_dir}")
        return 1
    
    capture_dirs = [d for d in args.captures_dir.iterdir() if d.is_dir()]
    
    if not capture_dirs:
        print(f"Error: No capture directories found in {args.captures_dir}")
        return 1
    
    print("="*80)
    print("EXTRACTING HOMEKIT-RELEVANT INFORMATION")
    print("="*80)
    print()
    
    results = analyze_captures(capture_dirs)
    
    # Display results
    print("📱 DEVICE METADATA")
    print("-" * 80)
    for metadata in results["device_metadata"]:
        print(f"\nDevice from {metadata['file']}:")
        print(f"  Device ID: {metadata['device_id']}")
        if metadata.get("serial_number"):
            print(f"  ✅ Serial Number: {metadata['serial_number']}")
        if metadata.get("device_type"):
            print(f"  Type: {metadata['device_type']}")
        if metadata.get("manufacturer"):
            print(f"  Manufacturer: {metadata['manufacturer']}")
        if metadata.get("model"):
            print(f"  Model: {metadata['model']}")
        if metadata.get("traits"):
            print(f"  Traits: {len(metadata['traits'])}")
            for trait in metadata["traits"][:5]:
                print(f"    - {trait}")
        if metadata.get("interfaces"):
            print(f"  Interfaces: {len(metadata['interfaces'])}")
            for iface in metadata["interfaces"][:5]:
                print(f"    - {iface}")
    
    print()
    print("="*80)
    print("HOMEKIT-RELEVANT FIELDS FOUND")
    print("="*80)
    
    for category, fields in results["homekit_fields"].items():
        if fields:
            print(f"\n{category.upper().replace('_', ' ')}: {len(fields)} field(s)")
            unique_fields = {}
            for field in fields:
                key = f"{field['full_path']}"
                if key not in unique_fields:
                    unique_fields[key] = field
            
            for field in list(unique_fields.values())[:10]:  # Show first 10
                value_str = str(field["value"])
                if len(value_str) > 80:
                    value_str = value_str[:80] + "..."
                print(f"  {field['full_path']}: {value_str}")
    
    # Save to JSON if requested
    if args.output:
        args.output.write_text(json.dumps(results, indent=2, default=str))
        print(f"\n✅ Results saved to: {args.output}")
    
    print()
    print("="*80)
    print("SUMMARY")
    print("="*80)
    print(f"Devices found: {len(results['device_metadata'])}")
    total_fields = sum(len(fields) for fields in results["homekit_fields"].values())
    print(f"HomeKit-relevant fields: {total_fields}")
    print()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

