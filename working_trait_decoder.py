#!/usr/bin/env python3
"""
Working trait decoder that processes messages the same way the handler does.

This simulates the actual stream processing to extract all trait data.
"""

import sys
import asyncio
from pathlib import Path
from typing import Dict, Any, List

# Import handler
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


async def process_raw_file(capture_file: Path) -> Dict[str, Any]:
    """Process raw file the same way the handler processes stream data."""
    handler = NestProtobufHandler()
    
    with open(capture_file, "rb") as f:
        raw_data = f.read()
    
    # Process using handler's ingest_chunk logic
    # The handler processes varint-prefixed messages
    all_traits = {}
    all_results = []
    
    pos = 0
    while pos < len(raw_data):
        # Decode varint length
        length, offset = handler._decode_varint(raw_data, pos)
        
        if length is None or length == 0:
            break
        
        if offset + length > len(raw_data):
            # Incomplete message
            break
        
        # Extract message
        message = raw_data[offset:offset + length]
        pos = offset + length
        
        # Process message using handler
        try:
            result = await handler._process_message(message)
            all_results.append(result)
        except Exception:
            pass  # Ignore processing errors
        
        # Try to extract traits from stream_body (even if DecodeError occurred)
        try:
            stream_body = handler.stream_body
            
            for msg in stream_body.message:
                for get_op in msg.get:
                    obj_id = get_op.object.id if get_op.object.id else None
                    property_any = getattr(get_op.data, "property", None)
                    
                    if not property_any:
                        continue
                    
                    property_any = _normalize_any_type(property_any)
                    type_url = property_any.type_url or ""
                    
                    if not type_url:
                        if hasattr(get_op, "data") and 7 in get_op.data:
                            type_url = "weave.trait.security.BoltLockTrait"
                        else:
                            continue
                    
                    trait_key = f"{obj_id}:{type_url}"
                    
                    # Decode trait
                    trait_info = {"object_id": obj_id, "type_url": type_url, "decoded": False}
                    
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
                        
                        # BoltLockTrait
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
                    
                    if trait_key not in all_traits or trait_info.get("decoded"):
                        all_traits[trait_key] = trait_info
        
        except Exception:
            pass  # Ignore errors in trait extraction
    
    return {
        "handler_results": all_results,
        "traits": all_traits,
    }


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Working trait decoder")
    parser.add_argument("--capture-dir", type=Path, help="Capture directory")
    parser.add_argument("--file", type=Path, help="Specific file")
    
    args = parser.parse_args()
    
    if args.file:
        files = [args.file]
    elif args.capture_dir:
        files = sorted(args.capture_dir.glob("*.raw.bin"))
    else:
        captures_dir = Path("captures")
        capture_dirs = sorted([d for d in captures_dir.iterdir() if d.is_dir()],
                            key=lambda x: x.stat().st_mtime, reverse=True)
        if not capture_dirs:
            print("Error: No captures found")
            return 1
        files = sorted(capture_dirs[0].glob("*.raw.bin"))
    
    print("="*80)
    print("WORKING TRAIT DECODER")
    print("="*80)
    
    all_traits_found = {}
    
    for raw_file in files:
        print(f"\n{'='*80}")
        print(f"Processing: {raw_file.name}")
        print(f"{'='*80}\n")
        
        result = asyncio.run(process_raw_file(raw_file))
        
        # Show handler results
        handler_results = result.get("handler_results", [])
        if handler_results:
            print("Handler Results:")
            for hr in handler_results:
                if hr.get("yale"):
                    print("  Lock data:")
                    for device_id, device_data in hr["yale"].items():
                        print(f"    Device: {device_id}")
                        for key, value in device_data.items():
                            print(f"      {key}: {value}")
                if hr.get("user_id"):
                    print(f"  User ID: {hr['user_id']}")
                if hr.get("structure_id"):
                    print(f"  Structure ID: {hr['structure_id']}")
            print()
        
        # Show decoded traits
        traits = result.get("traits", {})
        if traits:
            print(f"Decoded Traits ({len(traits)}):\n")
            
            for trait_key, trait_info in sorted(traits.items()):
                type_url = trait_info["type_url"]
                obj_id = trait_info["object_id"]
                
                if type_url not in all_traits_found:
                    all_traits_found[type_url] = []
                
                print(f"  {type_url}")
                print(f"    Object ID: {obj_id}")
                
                if trait_info.get("decoded"):
                    print(f"    ✅ Decoded")
                    for key, value in trait_info.get("data", {}).items():
                        if value is not None:
                            print(f"       {key}: {value}")
                            all_traits_found[type_url].append({key: value})
                elif "error" in trait_info:
                    print(f"    ❌ Error: {trait_info['error']}")
                else:
                    print(f"    ⚠️  No decoder")
                print()
        else:
            print("⚠️  No traits extracted")
    
    # Final summary
    print(f"\n{'='*80}")
    print("FINAL SUMMARY")
    print(f"{'='*80}\n")
    print(f"Unique traits found: {len(all_traits_found)}")
    for trait_type in sorted(all_traits_found.keys()):
        print(f"  - {trait_type}")
        if all_traits_found[trait_type]:
            print(f"    Data: {all_traits_found[trait_type]}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

