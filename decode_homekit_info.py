#!/usr/bin/env python3
"""
Decode HomeKit-relevant information from protobuf messages using proto definitions.

Extracts:
- Serial numbers (from DeviceIdentityTrait or device ID)
- Battery information (from BatteryPowerSourceTrait)
- Firmware versions (from DeviceIdentityTrait)
- Last contact timestamps
- Model/manufacturer information
"""

import sys
from pathlib import Path
from typing import Dict, Any, Optional

# Try to import proto definitions
try:
    import sys
    proto_path = Path(__file__).parent / "proto"
    sys.path.insert(0, str(proto_path))
    
    # Import proto modules
    from weave.trait.description import description_pb2
    from weave.trait.power import power_pb2
    from nest.trait.structure import structure_pb2
    PROTO_AVAILABLE = True
except ImportError as e:
    PROTO_AVAILABLE = False
    print(f"Warning: Proto definitions not available: {e}", file=sys.stderr)
    print("Some features will be limited.", file=sys.stderr)


def decode_device_identity_trait(trait_data: bytes) -> Dict[str, Any]:
    """Decode DeviceIdentityTrait to extract serial, firmware, model."""
    if not PROTO_AVAILABLE:
        return {}
    
    try:
        trait = description_pb2.DeviceIdentityTrait()
        trait.ParseFromString(trait_data)
        
        result = {}
        
        # Serial number (field 6)
        if trait.serial_number:
            result["serial_number"] = trait.serial_number
        
        # Firmware version (field 7)
        if trait.fw_version:
            result["firmware_version"] = trait.fw_version
        
        # Manufacturer (field 2 - String_Indirect)
        if trait.HasField("manufacturer"):
            result["manufacturer"] = trait.manufacturer.value
        
        # Model name (field 4 - String_Indirect)
        if trait.HasField("model_name"):
            result["model"] = trait.model_name.value
        
        return result
    except Exception as e:
        print(f"Error decoding DeviceIdentityTrait: {e}", file=sys.stderr)
        return {}


def decode_battery_power_source_trait(trait_data: bytes) -> Dict[str, Any]:
    """Decode BatteryPowerSourceTrait to extract battery information."""
    if not PROTO_AVAILABLE:
        return {}
    
    try:
        trait = power_pb2.BatteryPowerSourceTrait()
        trait.ParseFromString(trait_data)
        
        result = {}
        
        # Voltage (field 2)
        if trait.HasField("assessedVoltage"):
            result["voltage"] = trait.assessedVoltage.value
        
        # Current (field 3)
        if trait.HasField("assessedCurrent"):
            result["current"] = trait.assessedCurrent.value
        
        # Condition (field 5)
        if trait.condition:
            condition_map = {
                0: "UNSPECIFIED",
                1: "NOMINAL",
                2: "CRITICAL",
            }
            result["condition"] = condition_map.get(trait.condition, f"UNKNOWN_{trait.condition}")
        
        # Status (field 6)
        if trait.status:
            status_map = {
                0: "UNSPECIFIED",
                1: "ACTIVE",
                2: "STANDBY",
                3: "INACTIVE",
            }
            result["status"] = status_map.get(trait.status, f"UNKNOWN_{trait.status}")
        
        # Replacement indicator (field 32)
        if trait.replacementIndicator:
            replacement_map = {
                0: "UNSPECIFIED",
                1: "NOT_AT_ALL",
                2: "SOON",
                3: "IMMEDIATELY",
            }
            result["replacement_indicator"] = replacement_map.get(
                trait.replacementIndicator,
                f"UNKNOWN_{trait.replacementIndicator}"
            )
        
        # Battery remaining (field 33)
        if trait.HasField("remaining"):
            remaining = {}
            if trait.remaining.HasField("remainingPercent"):
                remaining["percent"] = trait.remaining.remainingPercent.value
            if trait.remaining.HasField("remainingTime"):
                # remainingTime is a Timer type - extract seconds if available
                remaining["time"] = str(trait.remaining.remainingTime)
            if remaining:
                result["battery_remaining"] = remaining
        
        return result
    except Exception as e:
        print(f"Error decoding BatteryPowerSourceTrait: {e}", file=sys.stderr)
        return {}


def decode_power_source_trait(trait_data: bytes) -> Dict[str, Any]:
    """Decode PowerSourceTrait to extract power information."""
    if not PROTO_AVAILABLE:
        return {}
    
    try:
        trait = power_pb2.PowerSourceTrait()
        trait.ParseFromString(trait_data)
        
        result = {}
        
        # Voltage
        if trait.HasField("assessedVoltage"):
            result["voltage"] = trait.assessedVoltage.value
        
        # Current
        if trait.HasField("assessedCurrent"):
            result["current"] = trait.assessedCurrent.value
        
        # Frequency
        if trait.HasField("assessedFrequency"):
            result["frequency"] = trait.assessedFrequency.value
        
        # Condition
        if trait.condition:
            condition_map = {
                0: "UNSPECIFIED",
                1: "NOMINAL",
                2: "CRITICAL",
            }
            result["condition"] = condition_map.get(trait.condition, f"UNKNOWN_{trait.condition}")
        
        # Status
        if trait.status:
            status_map = {
                0: "UNSPECIFIED",
                1: "ACTIVE",
                2: "STANDBY",
                3: "INACTIVE",
            }
            result["status"] = status_map.get(trait.status, f"UNKNOWN_{trait.status}")
        
        # Present
        result["present"] = trait.present
        
        return result
    except Exception as e:
        print(f"Error decoding PowerSourceTrait: {e}", file=sys.stderr)
        return {}


def extract_homekit_info_from_stream_body(stream_body_data: bytes) -> Dict[str, Any]:
    """Extract HomeKit information from a StreamBody message."""
    if not PROTO_AVAILABLE:
        return {}
    
    try:
        from nest.rpc import rpc_pb2
        
        stream_body = rpc_pb2.StreamBody()
        stream_body.ParseFromString(stream_body_data)
        
        homekit_info = {
            "serial_number": None,
            "firmware_version": None,
            "battery_info": {},
            "model_info": {},
            "timestamps": [],
        }
        
        # Process each resource in the stream
        for resource in stream_body.resources:
            # Extract device ID
            if resource.id.startswith("DEVICE_"):
                homekit_info["serial_number"] = resource.id.replace("DEVICE_", "")
            
            # Process traits
            for trait in resource.traits:
                trait_name = trait.name
                trait_data = trait.data
                
                # DeviceIdentityTrait
                if trait_name == "weave.trait.description.DeviceIdentityTrait":
                    identity = decode_device_identity_trait(trait_data)
                    if identity.get("serial_number"):
                        homekit_info["serial_number"] = identity["serial_number"]
                    if identity.get("firmware_version"):
                        homekit_info["firmware_version"] = identity["firmware_version"]
                    if identity.get("manufacturer") or identity.get("model"):
                        homekit_info["model_info"] = {
                            "manufacturer": identity.get("manufacturer"),
                            "model": identity.get("model"),
                        }
                
                # BatteryPowerSourceTrait
                elif trait_name == "weave.trait.power.BatteryPowerSourceTrait":
                    battery = decode_battery_power_source_trait(trait_data)
                    if battery:
                        homekit_info["battery_info"] = battery
                
                # PowerSourceTrait
                elif trait_name == "weave.trait.power.PowerSourceTrait":
                    power = decode_power_source_trait(trait_data)
                    if power:
                        homekit_info["battery_info"].update(power)
        
        return homekit_info
    
    except Exception as e:
        print(f"Error extracting HomeKit info: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return {}


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Decode HomeKit information from protobuf messages"
    )
    parser.add_argument(
        "input_file",
        type=Path,
        help="Raw protobuf message file (.raw.bin) or capture directory",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output JSON file",
    )
    
    args = parser.parse_args()
    
    if not args.input_file.exists():
        print(f"Error: Input file does not exist: {args.input_file}")
        return 1
    
    print("="*80)
    print("DECODING HOMEKIT INFORMATION")
    print("="*80)
    print()
    
    # Determine if it's a file or directory
    if args.input_file.is_dir():
        # Find .raw.bin files
        raw_files = list(args.input_file.glob("*.raw.bin"))
        if not raw_files:
            print(f"Error: No .raw.bin files found in {args.input_file}")
            return 1
        input_files = raw_files
    else:
        input_files = [args.input_file]
    
    all_results = {}
    for input_file in input_files:
        print(f"Processing: {input_file.name}")
        
        try:
            with open(input_file, "rb") as f:
                data = f.read()
            
            homekit_info = extract_homekit_info_from_stream_body(data)
            all_results[input_file.name] = homekit_info
            
            # Display results
            print(f"  Serial Number: {homekit_info.get('serial_number', 'Not found')}")
            print(f"  Firmware Version: {homekit_info.get('firmware_version', 'Not found')}")
            
            if homekit_info.get("battery_info"):
                print(f"  Battery Info:")
                for key, value in homekit_info["battery_info"].items():
                    print(f"    {key}: {value}")
            else:
                print(f"  Battery Info: Not found")
            
            if homekit_info.get("model_info"):
                print(f"  Model Info:")
                for key, value in homekit_info["model_info"].items():
                    print(f"    {key}: {value}")
            else:
                print(f"  Model Info: Not found")
            
            print()
        
        except Exception as e:
            print(f"Error processing {input_file}: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
    
    # Save to JSON if requested
    if args.output:
        import json
        args.output.write_text(json.dumps(all_results, indent=2, default=str))
        print(f"✅ Results saved to: {args.output}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

