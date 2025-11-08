#!/usr/bin/env python3
"""
Search for a specific serial number in captured protobuf messages.

Usage:
    python find_serial_number.py AHNJ2005298
    python find_serial_number.py --search-all
"""

import json
import sys
from pathlib import Path
from typing import Dict, Any, List


def search_for_serial(serial_number: str, capture_dir: Path) -> List[Dict[str, Any]]:
    """Search for serial number in all captures."""
    results = []
    
    for blackbox_file in capture_dir.rglob("*.blackbox.json"):
        try:
            with open(blackbox_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Search for serial number
            data_str = json.dumps(data)
            if serial_number in data_str:
                # Find exact locations
                locations = find_serial_locations(data, serial_number)
                if locations:
                    results.append({
                        "file": str(blackbox_file.relative_to(capture_dir)),
                        "locations": locations,
                    })
        except Exception as e:
            pass
    
    return results


def find_serial_locations(obj: Any, serial_number: str, path: str = "", depth: int = 0) -> List[Dict[str, Any]]:
    """Find all locations where serial number appears."""
    if depth > 20:
        return []
    
    locations = []
    
    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(value, str) and serial_number in value:
                locations.append({
                    "path": f"{path}.{key}" if path else str(key),
                    "key": key,
                    "value": value,
                    "field_number": key if isinstance(key, (int, str)) and str(key).isdigit() else None,
                })
            elif isinstance(value, (dict, list)):
                locations.extend(find_serial_locations(value, serial_number, f"{path}.{key}" if path else str(key), depth + 1))
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            locations.extend(find_serial_locations(item, serial_number, f"{path}[{idx}]" if path else f"[{idx}]", depth + 1))
    
    return locations


def extract_all_serial_numbers(capture_dir: Path) -> List[str]:
    """Extract all potential serial numbers from captures."""
    serials = set()
    
    def find_serials(obj, depth=0):
        if depth > 15:
            return
        if isinstance(obj, dict):
            # Field 6 in DeviceIdentityTrait is serial_number
            if "6" in obj and isinstance(obj["6"], str):
                val = obj["6"]
                # Look for alphanumeric strings that could be serial numbers
                if len(val) >= 8 and val.replace("-", "").replace("_", "").isalnum():
                    serials.add(val)
            for value in obj.values():
                find_serials(value, depth + 1)
        elif isinstance(obj, list):
            for item in obj:
                find_serials(item, depth + 1)
    
    for blackbox_file in capture_dir.rglob("*.blackbox.json"):
        try:
            with open(blackbox_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            find_serials(data)
        except Exception:
            pass
    
    return sorted(serials)


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Search for serial numbers in captured protobuf messages"
    )
    parser.add_argument(
        "serial_number",
        nargs="?",
        help="Serial number to search for (e.g., AHNJ2005298)",
    )
    parser.add_argument(
        "--search-all",
        action="store_true",
        help="Extract all serial numbers found in captures",
    )
    parser.add_argument(
        "--captures-dir",
        type=Path,
        default=Path("captures"),
        help="Directory containing captures",
    )
    
    args = parser.parse_args()
    
    if not args.captures_dir.exists():
        print(f"Error: Captures directory does not exist: {args.captures_dir}")
        return 1
    
    if args.search_all:
        print("="*80)
        print("EXTRACTING ALL SERIAL NUMBERS")
        print("="*80)
        print()
        
        serials = extract_all_serial_numbers(args.captures_dir)
        
        if serials:
            print(f"Found {len(serials)} serial number(s):")
            for serial in serials:
                print(f"  - {serial}")
        else:
            print("⚠️  No serial numbers found in captures")
            print()
            print("This likely means DeviceIdentityTrait was not captured.")
            print("Run: python capture_homekit_traits.py")
        
        return 0
    
    if not args.serial_number:
        parser.print_help()
        return 1
    
    serial_number = args.serial_number.upper()
    
    print("="*80)
    print(f"SEARCHING FOR SERIAL NUMBER: {serial_number}")
    print("="*80)
    print()
    
    results = search_for_serial(serial_number, args.captures_dir)
    
    if results:
        print(f"✅ Found serial number in {len(results)} file(s):")
        print()
        for result in results:
            print(f"File: {result['file']}")
            for loc in result["locations"]:
                print(f"  Path: {loc['path']}")
                if loc.get("field_number"):
                    print(f"  Field: {loc['field_number']} (DeviceIdentityTrait field 6 = serial_number)")
                print(f"  Value: {loc['value']}")
            print()
    else:
        print(f"⚠️  Serial number '{serial_number}' not found in existing captures")
        print()
        print("This means we need to capture with DeviceIdentityTrait to get the serial number.")
        print("The serial number should appear in field 6 of DeviceIdentityTrait.")
        print()
        print("To capture it, run:")
        print("  python capture_homekit_traits.py")
        print()
        print("Or check if it appears in a different format (device ID, etc.)")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

