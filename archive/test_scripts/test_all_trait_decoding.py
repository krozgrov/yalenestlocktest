#!/usr/bin/env python3
"""
Test decoding all traits from captured messages.

This script:
1. Loads captured raw messages
2. Attempts to decode each trait using proto definitions
3. Reports which traits decode successfully
4. Shows extracted data for each trait
"""

import sys
import json
from pathlib import Path
from typing import Dict, Any, List

# Add proto to path
sys.path.insert(0, str(Path(__file__).parent / "proto"))

try:
    from proto.nest import rpc_pb2
    from proto.weave.trait import description_pb2
    from proto.weave.trait import power_pb2
    from proto.weave.trait import security_pb2
    from proto.nest.trait import structure_pb2
    from proto.nest.trait import user_pb2
    from google.protobuf.any_pb2 import Any
    PROTO_AVAILABLE = True
except ImportError as e:
    PROTO_AVAILABLE = False
    print(f"Warning: Some proto modules not available: {e}", file=sys.stderr)


def decode_device_identity_trait(trait_data: bytes) -> Dict[str, Any]:
    """Decode DeviceIdentityTrait."""
    if not PROTO_AVAILABLE:
        return {}
    
    try:
        trait = description_pb2.DeviceIdentityTrait()
        trait.ParseFromString(trait_data)
        
        result = {}
        if trait.serial_number:
            result["serial_number"] = trait.serial_number
        if trait.fw_version:
            result["firmware_version"] = trait.fw_version
        if trait.HasField("manufacturer"):
            result["manufacturer"] = trait.manufacturer.value
        if trait.HasField("model_name"):
            result["model"] = trait.model_name.value
        return result
    except Exception as e:
        return {"error": str(e)}


def decode_battery_power_source_trait(trait_data: bytes) -> Dict[str, Any]:
    """Decode BatteryPowerSourceTrait."""
    if not PROTO_AVAILABLE:
        return {}
    
    try:
        trait = power_pb2.BatteryPowerSourceTrait()
        trait.ParseFromString(trait_data)
        
        result = {}
        if trait.HasField("remaining") and trait.remaining.HasField("remainingPercent"):
            result["battery_level"] = trait.remaining.remainingPercent.value
        if trait.replacementIndicator:
            result["replacement_indicator"] = trait.replacementIndicator
        if trait.HasField("assessedVoltage"):
            result["voltage"] = trait.assessedVoltage.value
        if trait.condition:
            result["condition"] = trait.condition
        if trait.status:
            result["status"] = trait.status
        return result
    except Exception as e:
        return {"error": str(e)}


def decode_bolt_lock_trait(trait_data: bytes) -> Dict[str, Any]:
    """Decode BoltLockTrait."""
    if not PROTO_AVAILABLE:
        return {}
    
    try:
        trait = security_pb2.BoltLockTrait()
        trait.ParseFromString(trait_data)
        
        result = {
            "locked_state": trait.lockedState,
            "actuator_state": trait.actuatorState,
        }
        if trait.HasField("boltLockActor"):
            if trait.boltLockActor.HasField("originator"):
                result["originator"] = trait.boltLockActor.originator.resourceId
        return result
    except Exception as e:
        return {"error": str(e)}


def decode_structure_info_trait(trait_data: bytes) -> Dict[str, Any]:
    """Decode StructureInfoTrait."""
    if not PROTO_AVAILABLE:
        return {}
    
    try:
        trait = structure_pb2.StructureInfoTrait()
        trait.ParseFromString(trait_data)
        
        result = {}
        if trait.legacy_id:
            result["legacy_id"] = trait.legacy_id
        if trait.ssid:
            result["ssid"] = trait.ssid
        return result
    except Exception as e:
        return {"error": str(e)}


def decode_user_info_trait(trait_data: bytes) -> Dict[str, Any]:
    """Decode UserInfoTrait."""
    if not PROTO_AVAILABLE:
        return {}
    
    try:
        trait = user_pb2.UserInfoTrait()
        trait.ParseFromString(trait_data)
        
        result = {}
        # Add fields as needed
        return result
    except Exception as e:
        return {"error": str(e)}


TRAIT_DECODERS = {
    "weave.trait.description.DeviceIdentityTrait": decode_device_identity_trait,
    "weave.trait.power.BatteryPowerSourceTrait": decode_battery_power_source_trait,
    "weave.trait.security.BoltLockTrait": decode_bolt_lock_trait,
    "nest.trait.structure.StructureInfoTrait": decode_structure_info_trait,
    "nest.trait.user.UserInfoTrait": decode_user_info_trait,
}


def decode_stream_body(raw_data: bytes) -> Dict[str, Any]:
    """Decode a StreamBody message and extract all traits."""
    if not PROTO_AVAILABLE:
        return {"error": "Proto modules not available"}
    
    results = {
        "resources": [],
        "decoded_traits": {},
        "errors": [],
    }
    
    try:
        stream_body = rpc_pb2.StreamBody()
        stream_body.ParseFromString(raw_data)
        
        # Process resources
        for resource in stream_body.resources:
            resource_info = {
                "id": resource.id,
                "type": resource.type,
                "traits": [],
            }
            
            # Process traits
            for trait in resource.traits:
                trait_name = trait.name
                trait_info = {
                    "name": trait_name,
                    "decoded": False,
                    "data": {},
                }
                
                # Get trait data
                trait_data = None
                if hasattr(trait, "data") and trait.data:
                    trait_data = trait.data
                elif hasattr(trait, "property"):
                    prop = trait.property
                    if hasattr(prop, "value"):
                        trait_data = prop.value
                
                if trait_data:
                    # Try to decode
                    decoder = TRAIT_DECODERS.get(trait_name)
                    if decoder:
                        decoded = decoder(trait_data)
                        if "error" not in decoded:
                            trait_info["decoded"] = True
                            trait_info["data"] = decoded
                            results["decoded_traits"][trait_name] = decoded
                        else:
                            trait_info["error"] = decoded["error"]
                            results["errors"].append(f"{trait_name}: {decoded['error']}")
                    else:
                        trait_info["note"] = "No decoder available"
                
                resource_info["traits"].append(trait_info)
            
            results["resources"].append(resource_info)
    
    except Exception as e:
        results["error"] = str(e)
        import traceback
        results["traceback"] = traceback.format_exc()
    
    return results


def test_capture_directory(capture_dir: Path) -> Dict[str, Any]:
    """Test decoding all messages in a capture directory."""
    print(f"\n{'='*80}")
    print(f"TESTING CAPTURE: {capture_dir.name}")
    print(f"{'='*80}\n")
    
    raw_files = sorted(capture_dir.glob("*.raw.bin"))
    
    if not raw_files:
        print("⚠️  No raw.bin files found")
        return {}
    
    all_results = {
        "total_files": len(raw_files),
        "successful_decodes": 0,
        "failed_decodes": 0,
        "traits_found": set(),
        "traits_decoded": set(),
        "traits_failed": set(),
        "results": [],
    }
    
    for raw_file in raw_files:
        print(f"Processing: {raw_file.name}")
        
        try:
            with open(raw_file, "rb") as f:
                raw_data = f.read()
            
            # Try to decode
            result = decode_stream_body(raw_data)
            
            if "error" in result:
                print(f"  ❌ Failed: {result['error']}")
                all_results["failed_decodes"] += 1
            else:
                print(f"  ✅ Decoded {len(result['resources'])} resource(s)")
                all_results["successful_decodes"] += 1
                
                # Track traits
                for resource in result["resources"]:
                    for trait in resource["traits"]:
                        all_results["traits_found"].add(trait["name"])
                        if trait["decoded"]:
                            all_results["traits_decoded"].add(trait["name"])
                            print(f"    ✅ {trait['name']}")
                            if trait["data"]:
                                for key, value in trait["data"].items():
                                    print(f"       {key}: {value}")
                        elif "error" in trait:
                            all_results["traits_failed"].add(trait["name"])
                            print(f"    ❌ {trait['name']}: {trait['error']}")
                        else:
                            print(f"    ⚠️  {trait['name']}: No decoder")
            
            all_results["results"].append({
                "file": raw_file.name,
                "result": result,
            })
        
        except Exception as e:
            print(f"  ❌ Error: {e}")
            all_results["failed_decodes"] += 1
    
    # Summary
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}\n")
    print(f"Files processed: {all_results['total_files']}")
    print(f"✅ Successful: {all_results['successful_decodes']}")
    print(f"❌ Failed: {all_results['failed_decodes']}")
    print(f"\nTraits found: {len(all_results['traits_found'])}")
    for trait in sorted(all_results['traits_found']):
        if trait in all_results['traits_decoded']:
            print(f"  ✅ {trait}")
        elif trait in all_results['traits_failed']:
            print(f"  ❌ {trait}")
        else:
            print(f"  ⚠️  {trait} (no decoder)")
    
    return all_results


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Test decoding all traits from captured messages"
    )
    parser.add_argument(
        "--capture-dir",
        type=Path,
        help="Specific capture directory to test",
    )
    parser.add_argument(
        "--captures-dir",
        type=Path,
        default=Path("captures"),
        help="Directory containing captures (uses latest if --capture-dir not specified)",
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
    print("TESTING ALL TRAIT DECODING")
    print("="*80)
    
    for capture_dir in capture_dirs:
        test_capture_directory(capture_dir)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

