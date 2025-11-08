#!/usr/bin/env python3
"""
Complete trait decoder that properly extracts and decodes all traits.

This fixes the gRPC-web message extraction and decodes all trait types.
"""

import sys
import asyncio
from pathlib import Path
from typing import Dict, Any

# Import handler and proto modules
from protobuf_handler import NestProtobufHandler
sys.path.insert(0, str(Path(__file__).parent / "proto"))

try:
    from proto.weave.trait import description_pb2
    from proto.weave.trait import power_pb2
    from proto.weave.trait import security_pb2
    from proto.nest.trait import structure_pb2
    from proto.nest.trait import user_pb2
    from proto.nest import rpc_pb2
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


def extract_protobuf_message(raw_data: bytes) -> bytes | None:
    """Extract the actual protobuf message from gRPC-web format."""
    # The handler processes messages using varint length prefixes
    # The raw.bin file contains the full response which may have multiple messages
    # We need to extract the first complete message
    
    pos = 0
    
    # Try gRPC-web frame format first (0x00 or 0x80)
    if len(raw_data) >= 5 and raw_data[0] in (0x00, 0x80):
        frame_type = raw_data[0]
        frame_len = int.from_bytes(raw_data[1:5], "big")
        
        if frame_type == 0x80:
            # Skip frame
            pos = 5 + frame_len
            if pos >= len(raw_data):
                return None
            # Continue with remaining data
            raw_data = raw_data[pos:]
            pos = 0
        
        if frame_type == 0x00 and frame_len > 0:
            # Data frame
            if len(raw_data) >= 5 + frame_len:
                return raw_data[5:5 + frame_len]
            return None
    
    # Try varint length prefix (used by handler)
    value = 0
    shift = 0
    start = pos
    max_bytes = 10
    
    while pos < len(raw_data) and pos < max_bytes and shift < 64:
        byte = raw_data[pos]
        value |= (byte & 0x7F) << shift
        pos += 1
        shift += 7
        if not (byte & 0x80):
            # Found complete varint
            if value > 0 and pos + value <= len(raw_data):
                return raw_data[pos:pos + value]
            break
        if pos - start >= max_bytes:
            break
    
    # If no length prefix found, the data might already be the message
    # But this is likely wrong - return None to indicate failure
    return None


def decode_all_traits(message: bytes) -> Dict[str, Any]:
    """Decode all traits from a protobuf message."""
    if not PROTO_AVAILABLE:
        return {"error": "Proto modules not available"}
    
    all_traits = {}
    
    try:
        stream_body = rpc_pb2.StreamBody()
        stream_body.ParseFromString(message)
        
        for msg in stream_body.message:
            for get_op in msg.get:
                obj_id = get_op.object.id if get_op.object.id else None
                property_any = getattr(get_op.data, "property", None)
                
                if not property_any:
                    continue
                
                property_any = _normalize_any_type(property_any)
                type_url = property_any.type_url or ""
                
                if not type_url:
                    # Try fallback for BoltLockTrait
                    if hasattr(get_op, "data") and 7 in get_op.data:
                        type_url = "weave.trait.security.BoltLockTrait"
                    else:
                        continue
                
                trait_key = f"{obj_id}:{type_url}"
                trait_info = {
                    "object_id": obj_id,
                    "type_url": type_url,
                    "decoded": False,
                    "data": {},
                }
                
                # Decode based on trait type
                try:
                    # DeviceIdentityTrait
                    if "DeviceIdentityTrait" in type_url:
                        trait = description_pb2.DeviceIdentityTrait()
                        property_any.Unpack(trait)
                        trait_info["decoded"] = True
                        trait_info["data"] = {
                            "serial_number": trait.serial_number if trait.serial_number else None,
                            "firmware_version": trait.fw_version if trait.fw_version else None,
                            "manufacturer": trait.manufacturer.value if trait.HasField("manufacturer") else None,
                            "model": trait.model_name.value if trait.HasField("model_name") else None,
                        }
                    
                    # BatteryPowerSourceTrait
                    elif "BatteryPowerSourceTrait" in type_url:
                        trait = power_pb2.BatteryPowerSourceTrait()
                        property_any.Unpack(trait)
                        trait_info["decoded"] = True
                        trait_info["data"] = {
                            "battery_level": trait.remaining.remainingPercent.value if trait.HasField("remaining") and trait.remaining.HasField("remainingPercent") else None,
                            "voltage": trait.assessedVoltage.value if trait.HasField("assessedVoltage") else None,
                            "condition": trait.condition,
                            "status": trait.status,
                            "replacement_indicator": trait.replacementIndicator,
                        }
                    
                    # BoltLockTrait (main one)
                    elif "BoltLockTrait" in type_url and "BoltLockSettings" not in type_url and "BoltLockCapabilities" not in type_url:
                        trait = security_pb2.BoltLockTrait()
                        property_any.Unpack(trait)
                        trait_info["decoded"] = True
                        trait_info["data"] = {
                            "locked_state": trait.lockedState,
                            "actuator_state": trait.actuatorState,
                            "originator": trait.boltLockActor.originator.resourceId if trait.HasField("boltLockActor") and trait.boltLockActor.HasField("originator") else None,
                        }
                    
                    # StructureInfoTrait
                    elif "StructureInfoTrait" in type_url:
                        trait = structure_pb2.StructureInfoTrait()
                        property_any.Unpack(trait)
                        trait_info["decoded"] = True
                        trait_info["data"] = {
                            "legacy_id": trait.legacy_id if trait.legacy_id else None,
                            "ssid": trait.ssid if trait.ssid else None,
                        }
                    
                    # UserInfoTrait
                    elif "UserInfoTrait" in type_url:
                        trait = user_pb2.UserInfoTrait()
                        property_any.Unpack(trait)
                        trait_info["decoded"] = True
                        trait_info["data"] = {"user_id": obj_id}
                
                except Exception as e:
                    trait_info["error"] = str(e)
                
                all_traits[trait_key] = trait_info
    
    except Exception as e:
        return {"error": str(e), "traceback": str(e.__traceback__)}
    
    return {"traits": all_traits}


async def test_capture_file(capture_file: Path):
    """Test decoding all traits from a capture file."""
    print(f"\n{'='*80}")
    print(f"Testing: {capture_file.name}")
    print(f"{'='*80}\n")
    
    try:
        with open(capture_file, "rb") as f:
            raw_data = f.read()
        
        print(f"Raw data: {len(raw_data)} bytes")
        
        # Extract protobuf message
        message = extract_protobuf_message(raw_data)
        
        if not message:
            print("❌ Could not extract protobuf message")
            return
        
        print(f"Extracted message: {len(message)} bytes\n")
        
        # Decode all traits
        result = decode_all_traits(message)
        
        if "error" in result:
            print(f"❌ Error: {result['error']}")
            return
        
        traits = result.get("traits", {})
        
        if not traits:
            print("⚠️  No traits found")
            return
        
        print(f"Found {len(traits)} trait(s):\n")
        
        decoded_count = 0
        failed_count = 0
        
        for trait_key, trait_info in sorted(traits.items()):
            type_url = trait_info["type_url"]
            obj_id = trait_info["object_id"]
            
            print(f"  {type_url}")
            print(f"    Object ID: {obj_id}")
            
            if trait_info.get("decoded"):
                decoded_count += 1
                print(f"    ✅ Decoded successfully")
                for key, value in trait_info.get("data", {}).items():
                    if value is not None:
                        print(f"       {key}: {value}")
            elif "error" in trait_info:
                failed_count += 1
                print(f"    ❌ Error: {trait_info['error']}")
            else:
                print(f"    ⚠️  No decoder available")
            print()
        
        print(f"{'='*80}")
        print("SUMMARY")
        print(f"{'='*80}\n")
        print(f"Total traits: {len(traits)}")
        print(f"✅ Decoded: {decoded_count}")
        print(f"❌ Failed: {failed_count}")
        print(f"⚠️  No decoder: {len(traits) - decoded_count - failed_count}")
    
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Complete trait decoder test")
    parser.add_argument("--capture-dir", type=Path, help="Capture directory")
    parser.add_argument("--file", type=Path, help="Specific file to test")
    
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
        capture_dirs = sorted([d for d in captures_dir.iterdir() if d.is_dir()],
                          key=lambda x: x.stat().st_mtime, reverse=True)
        if not capture_dirs:
            print("Error: No captures found")
            return 1
        capture_dir = capture_dirs[0]
        raw_files = sorted(capture_dir.glob("*.raw.bin"))
        for raw_file in raw_files:
            asyncio.run(test_capture_file(raw_file))
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

