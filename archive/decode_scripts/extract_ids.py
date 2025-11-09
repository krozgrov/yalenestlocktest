#!/usr/bin/env python3
"""
Extract Structure and User IDs from captured protobuf messages.

This script demonstrates how to extract structure and user IDs from
blackbox-decoded protobuf messages, which can then be used to improve
the integration.
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any, Optional


def extract_structure_id_from_blackbox(blackbox_data: Dict[str, Any]) -> Optional[str]:
    """Extract structure ID from blackbox decoded data."""
    def find_structure(obj: Any, depth: int = 0):
        if depth > 15:
            return None
        
        if isinstance(obj, dict):
            # Look for structure IDs
            if "1" in obj and isinstance(obj["1"], str):
                device_id = obj["1"]
                resource_type = obj.get("2", "")
                if not isinstance(resource_type, str):
                    resource_type = str(resource_type) if resource_type else ""
                
                # Check if it's a structure
                if "structure" in resource_type.lower() or device_id.startswith("STRUCTURE_"):
                    # Extract the ID part
                    if device_id.startswith("STRUCTURE_"):
                        return device_id.replace("STRUCTURE_", "")
                    return device_id
            
            # Also check for structure_info trait data
            if "10" in obj and isinstance(obj["10"], str):
                # This might be a structure name, check parent for ID
                pass
            
            # Recursively search
            for value in obj.values():
                result = find_structure(value, depth + 1)
                if result:
                    return result
        
        elif isinstance(obj, list):
            for item in obj:
                result = find_structure(item, depth + 1)
                if result:
                    return result
        
        return None
    
    return find_structure(blackbox_data)


def extract_user_id_from_blackbox(blackbox_data: Dict[str, Any]) -> Optional[str]:
    """Extract user ID from blackbox decoded data."""
    def find_user(obj: Any, depth: int = 0):
        if depth > 15:
            return None
        
        if isinstance(obj, dict):
            # Look for user IDs
            if "1" in obj and isinstance(obj["1"], str):
                device_id = obj["1"]
                resource_type = obj.get("2", "")
                if not isinstance(resource_type, str):
                    resource_type = str(resource_type) if resource_type else ""
                
                # Check if it's a user
                if "user" in resource_type.lower() or device_id.startswith("USER_"):
                    # Extract the ID part
                    if device_id.startswith("USER_"):
                        return device_id.replace("USER_", "")
                    return device_id
            
            # Recursively search
            for value in obj.values():
                result = find_user(value, depth + 1)
                if result:
                    return result
        
        elif isinstance(obj, list):
            for item in obj:
                result = find_user(item, depth + 1)
                if result:
                    return result
        
        return None
    
    return find_user(blackbox_data)


def extract_device_ids_from_blackbox(blackbox_data: Dict[str, Any]) -> list[Dict[str, Any]]:
    """Extract all device IDs from blackbox decoded data."""
    devices = []
    
    def find_devices(obj: Any, path: str = "", depth: int = 0):
        if depth > 15:
            return
        
        if isinstance(obj, dict):
            if "1" in obj and isinstance(obj["1"], str):
                device_id = obj["1"]
                resource_type = obj.get("2", "")
                if not isinstance(resource_type, str):
                    resource_type = str(resource_type) if resource_type else ""
                
                # Check if it's a device (lock, etc.)
                if ("yale" in resource_type.lower() or 
                    "linus" in resource_type.lower() or 
                    "lock" in resource_type.lower() or
                    device_id.startswith("DEVICE_")):
                    
                    # Extract traits
                    traits = []
                    if "4" in obj:
                        trait_list = obj["4"] if isinstance(obj["4"], list) else [obj["4"]]
                        for trait in trait_list:
                            if isinstance(trait, dict) and "2" in trait:
                                traits.append(trait["2"])
                    
                    devices.append({
                        "id": device_id,
                        "type": resource_type,
                        "traits": traits,
                    })
            
            # Recursively search
            for key, value in obj.items():
                find_devices(value, f"{path}.{key}" if path else key, depth + 1)
        
        elif isinstance(obj, list):
            for idx, item in enumerate(obj):
                find_devices(item, f"{path}[{idx}]" if path else f"[{idx}]", depth + 1)
    
    find_devices(blackbox_data)
    return devices


def analyze_capture(capture_dir: Path):
    """Analyze a capture directory and extract IDs."""
    print(f"Analyzing capture: {capture_dir.name}\n")
    print("=" * 80)
    
    # Find all blackbox JSON files
    blackbox_files = sorted(capture_dir.glob("*.blackbox.json"))
    
    if not blackbox_files:
        print("No blackbox JSON files found in this directory.")
        return
    
    all_structure_ids = set()
    all_user_ids = set()
    all_devices = []
    
    for blackbox_file in blackbox_files:
        print(f"\n📄 Analyzing: {blackbox_file.name}")
        print("-" * 80)
        
        with open(blackbox_file, "r", encoding="utf-8") as f:
            blackbox_data = json.load(f)
        
        # Extract IDs
        structure_id = extract_structure_id_from_blackbox(blackbox_data)
        user_id = extract_user_id_from_blackbox(blackbox_data)
        devices = extract_device_ids_from_blackbox(blackbox_data)
        
        if structure_id:
            print(f"✅ Structure ID: {structure_id}")
            all_structure_ids.add(structure_id)
        
        if user_id:
            print(f"✅ User ID: {user_id}")
            all_user_ids.add(user_id)
        
        if devices:
            print(f"✅ Devices found: {len(devices)}")
            for device in devices:
                print(f"   - {device['id']} ({device['type']})")
                if device.get('traits'):
                    print(f"     Traits: {', '.join(device['traits'][:3])}...")
                all_devices.append(device)
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    
    if all_structure_ids:
        print(f"\n📋 Structure IDs found: {len(all_structure_ids)}")
        for sid in sorted(all_structure_ids):
            print(f"   - {sid}")
    
    if all_user_ids:
        print(f"\n👤 User IDs found: {len(all_user_ids)}")
        for uid in sorted(all_user_ids):
            print(f"   - {uid}")
    
    if all_devices:
        print(f"\n🔒 Devices found: {len(all_devices)}")
        unique_devices = {d['id']: d for d in all_devices}.values()
        for device in unique_devices:
            print(f"   - {device['id']}")
            print(f"     Type: {device['type']}")
    
    print("\n" + "=" * 80)
    print("HOW TO USE THESE IDs")
    print("=" * 80)
    print("""
These IDs can be used in your integration:

1. Structure ID: Use this in API requests that require a structure ID
   Example: headers["X-Nest-Structure-Id"] = structure_id

2. User ID: Use this when sending commands that require a user ID
   Example: request.boltLockActor.originator.resourceId = user_id

3. Device IDs: Use these to identify which locks to control

To integrate this into your code, see the fallback_decoder.py module
or add similar extraction logic to your protobuf_handler.py
""")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Extract structure and user IDs from captured protobuf messages"
    )
    parser.add_argument(
        "capture_dir",
        type=Path,
        help="Directory containing captured protobuf messages",
    )
    
    args = parser.parse_args()
    
    if not args.capture_dir.exists():
        print(f"Error: Directory does not exist: {args.capture_dir}", file=sys.stderr)
        return 1
    
    analyze_capture(args.capture_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())

