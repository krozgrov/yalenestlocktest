#!/usr/bin/env python3
"""
Test trait decoding by enhancing the protobuf_handler to extract all traits.

This modifies the handler's _process_message to capture all trait data.
"""

import sys
import json
import asyncio
from pathlib import Path
from typing import Dict, Any

# Import proto modules
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


def _normalize_any_type(any_message: Any) -> Any:
    """Map legacy Nest type URLs onto googleapis prefix."""
    if not isinstance(any_message, Any):
        return any_message
    type_url = any_message.type_url or ""
    if type_url.startswith("type.nestlabs.com/"):
        normalized = Any()
        normalized.value = any_message.value
        normalized.type_url = type_url.replace("type.nestlabs.com/", "type.googleapis.com/", 1)
        return normalized
    return any_message


def extract_all_traits_from_message(message: bytes) -> Dict[str, Any]:
    """Extract all trait data from a protobuf message."""
    from proto.nest import rpc_pb2
    
    all_traits = {}
    
    try:
        stream_body = rpc_pb2.StreamBody()
        stream_body.ParseFromString(message)
        
        for msg in stream_body.message:
            for get_op in msg.get:
                obj_id = get_op.object.id if get_op.object.id else None
                property_any = getattr(get_op.data, "property", None)
                
                if property_any:
                    property_any = _normalize_any_type(property_any)
                    type_url = property_any.type_url or ""
                    
                    if not type_url:
                        continue
                    
                    trait_key = f"{obj_id}:{type_url}"
                    
                    # Try to decode based on type
                    decoded_data = {}
                    
                    try:
                        # DeviceIdentityTrait
                        if "DeviceIdentityTrait" in type_url:
                            trait = description_pb2.DeviceIdentityTrait()
                            property_any.Unpack(trait)
                            decoded_data = {
                                "serial_number": trait.serial_number,
                                "firmware_version": trait.fw_version,
                                "manufacturer": trait.manufacturer.value if trait.HasField("manufacturer") else None,
                                "model": trait.model_name.value if trait.HasField("model_name") else None,
                            }
                        
                        # BatteryPowerSourceTrait
                        elif "BatteryPowerSourceTrait" in type_url:
                            trait = power_pb2.BatteryPowerSourceTrait()
                            property_any.Unpack(trait)
                            decoded_data = {
                                "battery_level": trait.remaining.remainingPercent.value if trait.HasField("remaining") and trait.remaining.HasField("remainingPercent") else None,
                                "voltage": trait.assessedVoltage.value if trait.HasField("assessedVoltage") else None,
                                "condition": trait.condition,
                                "status": trait.status,
                                "replacement_indicator": trait.replacementIndicator,
                            }
                        
                        # BoltLockTrait
                        elif "BoltLockTrait" in type_url and "BoltLockSettings" not in type_url and "BoltLockCapabilities" not in type_url:
                            trait = security_pb2.BoltLockTrait()
                            property_any.Unpack(trait)
                            decoded_data = {
                                "locked_state": trait.lockedState,
                                "actuator_state": trait.actuatorState,
                                "originator": trait.boltLockActor.originator.resourceId if trait.HasField("boltLockActor") and trait.boltLockActor.HasField("originator") else None,
                            }
                        
                        # StructureInfoTrait
                        elif "StructureInfoTrait" in type_url:
                            trait = structure_pb2.StructureInfoTrait()
                            property_any.Unpack(trait)
                            decoded_data = {
                                "legacy_id": trait.legacy_id,
                                "ssid": trait.ssid,
                            }
                        
                        # UserInfoTrait
                        elif "UserInfoTrait" in type_url:
                            trait = user_pb2.UserInfoTrait()
                            property_any.Unpack(trait)
                            decoded_data = {"decoded": True}  # Add fields as needed
                    
                    except Exception as e:
                        decoded_data = {"error": str(e)}
                    
                    all_traits[trait_key] = {
                        "object_id": obj_id,
                        "type_url": type_url,
                        "decoded": len(decoded_data) > 0 and "error" not in decoded_data,
                        "data": decoded_data,
                    }
    
    except Exception as e:
        return {"error": str(e)}
    
    return {"traits": all_traits}


async def test_capture_file(capture_file: Path):
    """Test a single capture file."""
    print(f"\n{'='*80}")
    print(f"Testing: {capture_file.name}")
    print(f"{'='*80}\n")
    
    try:
        with open(capture_file, "rb") as f:
            raw_data = f.read()
        
        # Try to extract protobuf message from gRPC-web format
        # The raw.bin might be a full gRPC-web response, so we need to extract the message
        
        # Check if it starts with gRPC-web frame (0x00 or 0x80)
        if len(raw_data) >= 5 and raw_data[0] in (0x00, 0x80):
            # Extract length
            frame_len = int.from_bytes(raw_data[1:5], "big")
            if len(raw_data) >= 5 + frame_len:
                message = raw_data[5:5+frame_len]
            else:
                message = raw_data[5:]
        else:
            # Try varint length prefix
            pos = 0
            length = 0
            shift = 0
            while pos < len(raw_data) and pos < 10:
                byte = raw_data[pos]
                length |= (byte & 0x7F) << shift
                pos += 1
                if not (byte & 0x80):
                    break
                shift += 7
            
            if pos > 0 and pos < len(raw_data):
                message = raw_data[pos:]
            else:
                message = raw_data
        
        # Extract traits
        result = extract_all_traits_from_message(message)
        
        if "error" in result:
            print(f"❌ Error: {result['error']}")
            return
        
        traits = result.get("traits", {})
        
        if not traits:
            print("⚠️  No traits found")
            return
        
        print(f"Found {len(traits)} trait(s):\n")
        
        decoded_count = 0
        for trait_key, trait_info in sorted(traits.items()):
            obj_id, type_url = trait_key.split(":", 1)
            print(f"Trait: {type_url}")
            print(f"  Object ID: {obj_id}")
            
            if trait_info["decoded"]:
                decoded_count += 1
                print(f"  ✅ Decoded successfully")
                for key, value in trait_info["data"].items():
                    if value is not None:
                        print(f"     {key}: {value}")
            elif "error" in trait_info["data"]:
                print(f"  ❌ Error: {trait_info['data']['error']}")
            else:
                print(f"  ⚠️  No decoder available")
            print()
        
        print(f"Summary: {decoded_count}/{len(traits)} traits decoded successfully")
    
    except Exception as e:
        print(f"❌ Error processing file: {e}")
        import traceback
        traceback.print_exc()


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Test trait decoding from captured messages"
    )
    parser.add_argument(
        "--capture-dir",
        type=Path,
        help="Capture directory to test",
    )
    parser.add_argument(
        "--file",
        type=Path,
        help="Specific file to test",
    )
    
    args = parser.parse_args()
    
    if args.file:
        asyncio.run(test_capture_file(args.file))
    elif args.capture_dir:
        raw_files = sorted(args.capture_dir.glob("*.raw.bin"))
        for raw_file in raw_files:
            asyncio.run(test_capture_file(raw_file))
    else:
        # Use latest capture
        captures_dir = Path("captures")
        if not captures_dir.exists():
            print("Error: captures directory does not exist")
            return 1
        
        capture_dirs = sorted([d for d in captures_dir.iterdir() if d.is_dir()],
                            key=lambda x: x.stat().st_mtime, reverse=True)
        if not capture_dirs:
            print("Error: No capture directories found")
            return 1
        
        latest = capture_dirs[0]
        raw_files = sorted(latest.glob("*.raw.bin"))
        for raw_file in raw_files:
            asyncio.run(test_capture_file(raw_file))
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

