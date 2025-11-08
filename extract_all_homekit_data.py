#!/usr/bin/env python3
"""
Extract all HomeKit-relevant information from protobuf messages.

Extracts:
- Serial numbers
- Battery information  
- Firmware/software versions
- Last contact timestamps
- Device capabilities
- Model/manufacturer info
"""

import json
import sys
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime


def extract_serial_number(blackbox_data: Dict[str, Any]) -> str | None:
    """Extract serial number from device ID or DeviceIdentityTrait."""
    # Method 1: Look for DeviceIdentityTrait field 6 (serial_number) - this is the actual serial
    def find_serial_field(obj, depth=0):
        if depth > 15:
            return None
        if isinstance(obj, dict):
            # Field 6 in DeviceIdentityTrait is serial_number
            # Look for string values that look like serial numbers (alphanumeric, 8+ chars)
            if "6" in obj:
                val = obj["6"]
                if isinstance(val, str) and len(val) >= 8:
                    # Check if it looks like a serial number (alphanumeric)
                    if val.replace("-", "").replace("_", "").isalnum():
                        return val
            for value in obj.values():
                result = find_serial_field(value, depth+1)
                if result:
                    return result
        elif isinstance(obj, list):
            for item in obj:
                result = find_serial_field(item, depth+1)
                if result:
                    return result
        return None
    
    serial = find_serial_field(blackbox_data)
    if serial:
        return serial
    
    # Method 2: From device ID (fallback - this is usually a different format)
    def find_device_id(obj):
        if isinstance(obj, dict):
            if "1" in obj and isinstance(obj["1"], str) and obj["1"].startswith("DEVICE_"):
                # Device ID format is usually different from serial number
                # Return it but note it's a device ID, not necessarily the serial
                return obj["1"].replace("DEVICE_", "")
            for value in obj.values():
                result = find_device_id(value)
                if result:
                    return result
        elif isinstance(obj, list):
            for item in obj:
                result = find_device_id(item)
                if result:
                    return result
        return None
    
    device_id = find_device_id(blackbox_data)
    # Only return device ID if it looks like a serial number format
    if device_id and len(device_id) >= 8 and device_id.replace("-", "").replace("_", "").isalnum():
        return device_id
    
    return None


def extract_firmware_version(blackbox_data: Dict[str, Any]) -> str | None:
    """Extract firmware version from DeviceIdentityTrait field 7."""
    def find_fw_version(obj, depth=0):
        if depth > 15:
            return None
        if isinstance(obj, dict):
            # Field 7 in DeviceIdentityTrait is fw_version
            if "7" in obj:
                val = obj["7"]
                if isinstance(val, str) and len(val) > 0:
                    return val
            for value in obj.values():
                result = find_fw_version(value, depth+1)
                if result:
                    return result
        elif isinstance(obj, list):
            for item in obj:
                result = find_fw_version(item, depth+1)
                if result:
                    return result
        return None
    
    return find_fw_version(blackbox_data)


def extract_battery_info(blackbox_data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract battery information from PowerTrait or BatteryPowerSourceTrait."""
    battery_info = {}
    
    def find_battery_data(obj, path="", depth=0):
        if depth > 15:
            return
        
        if isinstance(obj, dict):
            # Look for battery-related fields
            # BatteryPowerSourceTrait has:
            # - field 33: BatteryRemaining with field 1: remainingPercent
            # - field 32: replacementIndicator
            
            if "33" in obj and isinstance(obj["33"], dict):
                # BatteryRemaining
                if "1" in obj["33"]:
                    battery_info["remaining_percent"] = obj["33"]["1"]
                if "2" in obj["33"]:
                    battery_info["remaining_time"] = obj["33"]["2"]
            
            if "32" in obj:
                battery_info["replacement_indicator"] = obj["32"]
            
            # PowerSourceTrait fields
            if "2" in obj:  # assessedVoltage
                try:
                    val = float(obj["2"]) if isinstance(obj["2"], (int, float, str)) else None
                    if val and 0 < val < 50:  # Reasonable voltage range
                        battery_info["voltage"] = val
                except:
                    pass
            
            if "5" in obj:  # condition
                battery_info["condition"] = obj["5"]
            
            if "6" in obj:  # status
                battery_info["status"] = obj["6"]
            
            # Recursively search
            for key, value in obj.items():
                find_battery_data(value, f"{path}.{key}" if path else str(key), depth + 1)
        
        elif isinstance(obj, list):
            for idx, item in enumerate(obj):
                find_battery_data(item, f"{path}[{idx}]" if path else f"[{idx}]", depth + 1)
    
    find_battery_data(blackbox_data)
    return battery_info


def extract_timestamps(blackbox_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract timestamp values that might indicate last contact."""
    timestamps = []
    
    def find_timestamps(obj, path="", depth=0):
        if depth > 15:
            return
        
        if isinstance(obj, dict):
            for key, value in obj.items():
                if isinstance(value, (int, str)):
                    try:
                        val = int(value) if isinstance(value, str) else value
                        # Check if it looks like a Unix timestamp
                        if 1000000000 < val < 9999999999:
                            try:
                                dt = datetime.fromtimestamp(val)
                                timestamps.append({
                                    "path": f"{path}.{key}" if path else str(key),
                                    "timestamp": val,
                                    "datetime": dt.isoformat(),
                                })
                            except:
                                pass
                    except:
                        pass
                
                find_timestamps(value, f"{path}.{key}" if path else str(key), depth + 1)
        
        elif isinstance(obj, list):
            for idx, item in enumerate(obj):
                find_timestamps(item, f"{path}[{idx}]" if path else f"[{idx}]", depth + 1)
    
    find_timestamps(blackbox_data)
    return timestamps


def extract_model_info(blackbox_data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract model and manufacturer information."""
    model_info = {}
    
    def find_model_info(obj, depth=0):
        if depth > 15:
            return
        
        if isinstance(obj, dict):
            # DeviceIdentityTrait fields:
            # - field 2: manufacturer (String_Indirect)
            # - field 4: model_name (String_Indirect)
            
            if "2" in obj:
                # Could be manufacturer
                if isinstance(obj["2"], dict) and "1" in obj["2"]:
                    model_info["manufacturer"] = obj["2"]["1"]
                elif isinstance(obj["2"], str) and len(obj["2"]) > 2:
                    if "yale" in obj["2"].lower() or "nest" in obj["2"].lower():
                        model_info["manufacturer"] = obj["2"]
            
            if "4" in obj:
                # Could be model_name
                if isinstance(obj["4"], dict) and "1" in obj["4"]:
                    model_info["model"] = obj["4"]["1"]
                elif isinstance(obj["4"], str) and len(obj["4"]) > 2:
                    model_info["model"] = obj["4"]
            
            # Also check resource type
            if "2" in obj and isinstance(obj["2"], str):
                resource_type = obj["2"]
                if "yale" in resource_type.lower():
                    model_info["manufacturer"] = "Yale"
                if "linus" in resource_type.lower():
                    model_info["model"] = "Linus Lock"
            
            for value in obj.values():
                find_model_info(value, depth + 1)
        
        elif isinstance(obj, list):
            for item in obj:
                find_model_info(item, depth + 1)
    
    find_model_info(blackbox_data)
    return model_info


def analyze_capture(capture_dir: Path) -> Dict[str, Any]:
    """Analyze a capture directory for HomeKit information."""
    results = {
        "serial_numbers": set(),
        "firmware_versions": set(),
        "battery_info": [],
        "timestamps": [],
        "model_info": {},
        "devices": [],
    }
    
    for blackbox_file in sorted(capture_dir.glob("*.blackbox.json")):
        try:
            with open(blackbox_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Extract serial number
            serial = extract_serial_number(data)
            if serial:
                results["serial_numbers"].add(serial)
            
            # Extract firmware
            fw_version = extract_firmware_version(data)
            if fw_version:
                results["firmware_versions"].add(fw_version)
            
            # Extract battery info
            battery = extract_battery_info(data)
            if battery:
                battery["source_file"] = blackbox_file.name
                results["battery_info"].append(battery)
            
            # Extract timestamps
            timestamps = extract_timestamps(data)
            results["timestamps"].extend(timestamps)
            
            # Extract model info
            model_info = extract_model_info(data)
            if model_info:
                results["model_info"].update(model_info)
            
            # Extract device info
            def find_devices(obj, depth=0):
                if depth > 15:
                    return []
                devices = []
                if isinstance(obj, dict):
                    if "1" in obj and isinstance(obj["1"], str) and obj["1"].startswith("DEVICE_"):
                        device = {
                            "id": obj["1"],
                            "type": obj.get("2", ""),
                            "traits": [],
                        }
                        if "4" in obj:
                            trait_list = obj["4"] if isinstance(obj["4"], list) else [obj["4"]]
                            for trait in trait_list:
                                if isinstance(trait, dict) and "2" in trait:
                                    device["traits"].append(trait["2"])
                        devices.append(device)
                    for value in obj.values():
                        devices.extend(find_devices(value, depth + 1))
                elif isinstance(obj, list):
                    for item in obj:
                        devices.extend(find_devices(item, depth + 1))
                return devices
            
            devices = find_devices(data)
            results["devices"].extend(devices)
        
        except Exception as e:
            print(f"Warning: Could not process {blackbox_file}: {e}", file=sys.stderr)
    
    # Convert sets to lists
    results["serial_numbers"] = list(results["serial_numbers"])
    results["firmware_versions"] = list(results["firmware_versions"])
    
    return results


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Extract all HomeKit-relevant information from captures"
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
        help="Directory containing captures (uses latest if --capture-dir not specified)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output JSON file",
    )
    
    args = parser.parse_args()
    
    if args.capture_dir:
        capture_dirs = [args.capture_dir]
    else:
        if not args.captures_dir.exists():
            print(f"Error: Captures directory does not exist: {args.captures_dir}")
            return 1
        capture_dirs = sorted([d for d in args.captures_dir.iterdir() if d.is_dir()],
                            key=lambda x: x.stat().st_mtime, reverse=True)
        if not capture_dirs:
            print(f"Error: No capture directories found")
            return 1
        capture_dirs = capture_dirs[:1]  # Use latest
    
    print("="*80)
    print("EXTRACTING HOMEKIT-RELEVANT INFORMATION")
    print("="*80)
    print()
    
    all_results = {}
    for capture_dir in capture_dirs:
        print(f"Analyzing: {capture_dir.name}")
        results = analyze_capture(capture_dir)
        all_results[capture_dir.name] = results
    
    # Display results
    print()
    print("="*80)
    print("HOMEKIT INFORMATION EXTRACTED")
    print("="*80)
    print()
    
    for capture_name, results in all_results.items():
        print(f"Capture: {capture_name}")
        print("-" * 80)
        
        if results["serial_numbers"]:
            print(f"✅ Serial Numbers: {', '.join(results['serial_numbers'])}")
        else:
            print("⚠️  Serial Numbers: Not found (may need DeviceIdentityTrait)")
        
        if results["firmware_versions"]:
            print(f"✅ Firmware Versions: {', '.join(results['firmware_versions'])}")
        else:
            print("⚠️  Firmware Versions: Not found (may need DeviceIdentityTrait)")
        
        if results["battery_info"]:
            print(f"✅ Battery Information: {len(results['battery_info'])} instance(s)")
            for battery in results["battery_info"]:
                print(f"   From {battery.get('source_file', 'unknown')}:")
                for key, value in battery.items():
                    if key != "source_file":
                        print(f"     {key}: {value}")
        else:
            print("⚠️  Battery Information: Not found (may need PowerTrait)")
        
        if results["timestamps"]:
            print(f"✅ Timestamps: {len(results['timestamps'])} found")
            for ts in results["timestamps"][:3]:
                print(f"   {ts['path']}: {ts['datetime']} ({ts['timestamp']})")
        else:
            print("⚠️  Timestamps: Not found")
        
        if results["model_info"]:
            print(f"✅ Model Information:")
            for key, value in results["model_info"].items():
                print(f"   {key}: {value}")
        else:
            print("⚠️  Model Information: Partial (from resource type)")
        
        if results["devices"]:
            print(f"✅ Devices: {len(results['devices'])} found")
            for device in results["devices"]:
                print(f"   {device['id']}")
                print(f"     Type: {device['type']}")
                print(f"     Traits: {len(device['traits'])}")
        
        print()
    
    # Recommendations
    print("="*80)
    print("RECOMMENDATIONS")
    print("="*80)
    print()
    print("To get more HomeKit information, capture with these traits:")
    print("  - weave.trait.description.DeviceIdentityTrait (serial, firmware, model)")
    print("  - weave.trait.power.PowerTrait (battery status)")
    print("  - weave.trait.power.BatteryPowerSourceTrait (battery level, replacement indicator)")
    print()
    print("Run:")
    print("  python capture_homekit_traits.py")
    print()
    
    # Save to JSON if requested
    if args.output:
        args.output.write_text(json.dumps(all_results, indent=2, default=str))
        print(f"✅ Results saved to: {args.output}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

