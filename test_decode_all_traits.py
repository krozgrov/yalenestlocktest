#!/usr/bin/env python3
"""
Test decoding all traits using the protobuf_handler approach.

This properly handles gRPC-web format messages and extracts all traits.
"""

import sys
import json
import asyncio
from pathlib import Path
from typing import Dict, Any, Set

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


def decode_trait_data(trait_name: str, trait_data: bytes) -> Dict[str, Any]:
    """Decode trait data based on trait name."""
    if not PROTO_AVAILABLE:
        return {}
    
    try:
        # DeviceIdentityTrait
        if "DeviceIdentityTrait" in trait_name:
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
        
        # BatteryPowerSourceTrait
        elif "BatteryPowerSourceTrait" in trait_name:
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
        
        # BoltLockTrait
        elif "BoltLockTrait" in trait_name and "BoltLock" in trait_name:
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
        
        # StructureInfoTrait
        elif "StructureInfoTrait" in trait_name:
            trait = structure_pb2.StructureInfoTrait()
            trait.ParseFromString(trait_data)
            result = {}
            if trait.legacy_id:
                result["legacy_id"] = trait.legacy_id
            if trait.ssid:
                result["ssid"] = trait.ssid
            return result
        
        # UserInfoTrait
        elif "UserInfoTrait" in trait_name:
            trait = user_pb2.UserInfoTrait()
            trait.ParseFromString(trait_data)
            result = {}
            # Add fields as needed
            return result
        
    except Exception as e:
        return {"error": str(e)}
    
    return {}


async def process_message(handler: NestProtobufHandler, message: bytes) -> Dict[str, Any]:
    """Process a message using the protobuf handler and extract all traits."""
    result = await handler._process_message(message)
    
    # Also extract trait data from stream_body
    decoded_traits = {}
    
    try:
        # Access the stream_body that was parsed
        stream_body = handler.stream_body
        
        # Process all resources and traits
        for msg in stream_body.message:
            for get_op in msg.get:
                property_any = getattr(get_op.data, "property", None)
                
                if property_any:
                    # Normalize type URL
                    type_url = property_any.type_url or ""
                    if type_url.startswith("type.nestlabs.com/"):
                        type_url = type_url.replace("type.nestlabs.com/", "type.googleapis.com/", 1)
                    
                    # Extract trait data
                    trait_data = property_any.value if hasattr(property_any, "value") else None
                    
                    if trait_data:
                        decoded = decode_trait_data(type_url, trait_data)
                        if decoded and "error" not in decoded:
                            decoded_traits[type_url] = decoded
    
    except Exception as e:
        pass  # Ignore errors in trait extraction
    
    return {
        "handler_result": result,
        "decoded_traits": decoded_traits,
    }


def test_capture_directory(capture_dir: Path):
    """Test decoding all messages in a capture directory."""
    print(f"\n{'='*80}")
    print(f"TESTING CAPTURE: {capture_dir.name}")
    print(f"{'='*80}\n")
    
    raw_files = sorted(capture_dir.glob("*.raw.bin"))
    
    if not raw_files:
        print("⚠️  No raw.bin files found")
        return
    
    handler = NestProtobufHandler()
    
    all_traits_found = set()
    all_traits_decoded = set()
    all_traits_failed = set()
    
    for raw_file in raw_files:
        print(f"Processing: {raw_file.name}")
        
        try:
            with open(raw_file, "rb") as f:
                raw_data = f.read()
            
            # Process using handler (handles gRPC-web format)
            results = asyncio.run(process_message(handler, raw_data))
            
            handler_result = results["handler_result"]
            decoded_traits = results["decoded_traits"]
            
            print(f"  ✅ Processed message")
            
            # Show handler results
            if handler_result.get("yale"):
                print(f"  Lock data:")
                for device_id, device_data in handler_result["yale"].items():
                    print(f"    Device: {device_id}")
                    for key, value in device_data.items():
                        print(f"      {key}: {value}")
            
            if handler_result.get("user_id"):
                print(f"  User ID: {handler_result['user_id']}")
            
            if handler_result.get("structure_id"):
                print(f"  Structure ID: {handler_result['structure_id']}")
            
            # Show decoded traits
            if decoded_traits:
                print(f"  Decoded traits:")
                for trait_name, trait_data in decoded_traits.items():
                    all_traits_found.add(trait_name)
                    all_traits_decoded.add(trait_name)
                    print(f"    ✅ {trait_name}")
                    for key, value in trait_data.items():
                        print(f"       {key}: {value}")
            
            # Check stream_body for all traits
            try:
                stream_body = handler.stream_body
                for msg in stream_body.message:
                    for get_op in msg.get:
                        property_any = getattr(get_op.data, "property", None)
                        if property_any:
                            type_url = property_any.type_url or ""
                            if type_url:
                                all_traits_found.add(type_url)
                                if type_url not in decoded_traits:
                                    print(f"    ⚠️  {type_url} (not decoded)")
            except:
                pass
        
        except Exception as e:
            print(f"  ❌ Error: {e}")
            import traceback
            traceback.print_exc()
    
    # Summary
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}\n")
    print(f"Traits found: {len(all_traits_found)}")
    print(f"Traits decoded: {len(all_traits_decoded)}")
    print(f"Traits not decoded: {len(all_traits_found - all_traits_decoded)}")
    print()
    
    for trait in sorted(all_traits_found):
        if trait in all_traits_decoded:
            print(f"  ✅ {trait}")
        else:
            print(f"  ⚠️  {trait} (needs decoder)")


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

