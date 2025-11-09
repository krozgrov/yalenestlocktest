#!/usr/bin/env python3
"""
Comprehensive test of all trait decoding in the test project.

This script:
1. Uses the actual protobuf_handler to process messages (handles gRPC-web format)
2. Extracts trait data from the parsed stream_body
3. Tests decoding each trait type
4. Reports success/failure for each trait
5. Shows all extracted data
"""

import sys
import json
import asyncio
from pathlib import Path
from typing import Dict, Any, Set, List

# Import the protobuf handler
from protobuf_handler import NestProtobufHandler

# Import proto modules for decoding
sys.path.insert(0, str(Path(__file__).parent / "proto"))

try:
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


def decode_trait_from_any(property_any: Any) -> Dict[str, Any]:
    """Decode a trait from a google.protobuf.Any message."""
    if not PROTO_AVAILABLE or not property_any:
        return {}
    
    type_url = property_any.type_url or ""
    
    # Normalize type URL
    if type_url.startswith("type.nestlabs.com/"):
        type_url = type_url.replace("type.nestlabs.com/", "type.googleapis.com/", 1)
    
    trait_data = property_any.value if hasattr(property_any, "value") else None
    if not trait_data:
        return {}
    
    result = {"type_url": type_url, "decoded": False, "data": {}}
    
    try:
        # DeviceIdentityTrait
        if "DeviceIdentityTrait" in type_url:
            trait = description_pb2.DeviceIdentityTrait()
            property_any.Unpack(trait)
            result["data"] = {
                "serial_number": trait.serial_number if trait.serial_number else None,
                "firmware_version": trait.fw_version if trait.fw_version else None,
                "manufacturer": trait.manufacturer.value if trait.HasField("manufacturer") else None,
                "model": trait.model_name.value if trait.HasField("model_name") else None,
            }
            result["decoded"] = True
        
        # BatteryPowerSourceTrait
        elif "BatteryPowerSourceTrait" in type_url:
            trait = power_pb2.BatteryPowerSourceTrait()
            property_any.Unpack(trait)
            result["data"] = {
                "battery_level": trait.remaining.remainingPercent.value if trait.HasField("remaining") and trait.remaining.HasField("remainingPercent") else None,
                "voltage": trait.assessedVoltage.value if trait.HasField("assessedVoltage") else None,
                "condition": trait.condition,
                "status": trait.status,
                "replacement_indicator": trait.replacementIndicator,
            }
            result["decoded"] = True
        
        # BoltLockTrait
        elif "BoltLockTrait" in type_url and "BoltLockSettings" not in type_url and "BoltLockCapabilities" not in type_url:
            trait = security_pb2.BoltLockTrait()
            property_any.Unpack(trait)
            result["data"] = {
                "locked_state": trait.lockedState,
                "actuator_state": trait.actuatorState,
                "originator": trait.boltLockActor.originator.resourceId if trait.HasField("boltLockActor") and trait.boltLockActor.HasField("originator") else None,
            }
            result["decoded"] = True
        
        # StructureInfoTrait
        elif "StructureInfoTrait" in type_url:
            trait = structure_pb2.StructureInfoTrait()
            property_any.Unpack(trait)
            result["data"] = {
                "legacy_id": trait.legacy_id if trait.legacy_id else None,
                "ssid": trait.ssid if trait.ssid else None,
            }
            result["decoded"] = True
        
        # UserInfoTrait
        elif "UserInfoTrait" in type_url:
            trait = user_pb2.UserInfoTrait()
            property_any.Unpack(trait)
            result["data"] = {}  # Add fields as needed
            result["decoded"] = True
        
        else:
            result["data"] = {"note": "No decoder implemented"}
    
    except Exception as e:
        result["error"] = str(e)
        import traceback
        result["traceback"] = traceback.format_exc()
    
    return result


async def process_capture_file(capture_file: Path, handler: NestProtobufHandler) -> Dict[str, Any]:
    """Process a single capture file and extract all trait data."""
    print(f"\nProcessing: {capture_file.name}")
    
    try:
        with open(capture_file, "rb") as f:
            raw_data = f.read()
        
        # Process using handler
        handler_result = await handler._process_message(raw_data)
        
        # Extract traits from stream_body
        decoded_traits = {}
        
        try:
            stream_body = handler.stream_body
            
            for msg in stream_body.message:
                for get_op in msg.get:
                    property_any = getattr(get_op.data, "property", None)
                    
                    if property_any:
                        decoded = decode_trait_from_any(property_any)
                        if decoded:
                            type_url = decoded["type_url"]
                            decoded_traits[type_url] = decoded
        except Exception as e:
            pass  # Ignore extraction errors
        
        return {
            "file": capture_file.name,
            "handler_result": handler_result,
            "decoded_traits": decoded_traits,
            "success": True,
        }
    
    except Exception as e:
        return {
            "file": capture_file.name,
            "error": str(e),
            "success": False,
        }


def test_capture_directory(capture_dir: Path):
    """Test all messages in a capture directory."""
    print(f"\n{'='*80}")
    print(f"TESTING CAPTURE: {capture_dir.name}")
    print(f"{'='*80}")
    
    raw_files = sorted(capture_dir.glob("*.raw.bin"))
    
    if not raw_files:
        print("⚠️  No raw.bin files found")
        return
    
    handler = NestProtobufHandler()
    
    all_results = []
    all_traits_found = set()
    all_traits_decoded = set()
    all_traits_failed = set()
    
    for raw_file in raw_files:
        result = asyncio.run(process_capture_file(raw_file, handler))
        all_results.append(result)
        
        if result["success"]:
            print(f"  ✅ Processed successfully")
            
            # Show handler results
            handler_result = result["handler_result"]
            if handler_result.get("yale"):
                print(f"  Lock data:")
                for device_id, device_data in handler_result["yale"].items():
                    print(f"    Device: {device_id}")
                    for key, value in device_data.items():
                        print(f"      {key}: {value}")
            
            # Show decoded traits
            decoded_traits = result["decoded_traits"]
            if decoded_traits:
                print(f"  Decoded traits:")
                for trait_name, trait_info in decoded_traits.items():
                    all_traits_found.add(trait_name)
                    
                    if trait_info.get("decoded"):
                        all_traits_decoded.add(trait_name)
                        print(f"    ✅ {trait_name}")
                        for key, value in trait_info.get("data", {}).items():
                            if value is not None:
                                print(f"       {key}: {value}")
                    elif "error" in trait_info:
                        all_traits_failed.add(trait_name)
                        print(f"    ❌ {trait_name}: {trait_info['error']}")
                    else:
                        print(f"    ⚠️  {trait_name}: {trait_info.get('data', {}).get('note', 'Unknown')}")
        else:
            print(f"  ❌ Failed: {result.get('error', 'Unknown error')}")
    
    # Summary
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}\n")
    print(f"Files processed: {len(raw_files)}")
    print(f"Successful: {sum(1 for r in all_results if r['success'])}")
    print(f"Failed: {sum(1 for r in all_results if not r['success'])}")
    print()
    print(f"Traits found: {len(all_traits_found)}")
    print(f"Traits decoded: {len(all_traits_decoded)}")
    print(f"Traits failed: {len(all_traits_failed)}")
    print(f"Traits not decoded: {len(all_traits_found - all_traits_decoded - all_traits_failed)}")
    print()
    
    print("Trait Status:")
    for trait in sorted(all_traits_found):
        if trait in all_traits_decoded:
            print(f"  ✅ {trait}")
        elif trait in all_traits_failed:
            print(f"  ❌ {trait}")
        else:
            print(f"  ⚠️  {trait} (no decoder)")
    
    return all_results


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Comprehensive test of all trait decoding"
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
    print("COMPREHENSIVE TRAIT DECODING TEST")
    print("="*80)
    
    for capture_dir in capture_dirs:
        test_capture_directory(capture_dir)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

