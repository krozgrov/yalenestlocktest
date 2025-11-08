#!/usr/bin/env python3
"""
Extract and decode all messages from a raw.bin file.

The file contains multiple protobuf messages, each with a varint length prefix.
"""

import sys
from pathlib import Path
from typing import List, Dict, Any

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


def extract_all_messages(raw_data: bytes) -> List[bytes]:
    """Extract all protobuf messages from raw data."""
    handler = NestProtobufHandler()
    messages = []
    pos = 0
    
    while pos < len(raw_data):
        length, offset = handler._decode_varint(raw_data, pos)
        
        if length is None or length == 0:
            break
        
        if offset + length <= len(raw_data):
            message = raw_data[offset:offset + length]
            messages.append(message)
            pos = offset + length
        else:
            # Incomplete message
            break
    
    return messages


def decode_trait(property_any: Any, type_url: str) -> Dict[str, Any]:
    """Decode a trait from property_any."""
    if not PROTO_AVAILABLE or not property_any:
        return {}
    
    result = {"decoded": False, "data": {}}
    
    try:
        property_any = _normalize_any_type(property_any)
        
        # DeviceIdentityTrait
        if "DeviceIdentityTrait" in type_url:
            trait = description_pb2.DeviceIdentityTrait()
            property_any.Unpack(trait)
            result["decoded"] = True
            result["data"] = {
                "serial_number": trait.serial_number if trait.serial_number else None,
                "firmware_version": trait.fw_version if trait.fw_version else None,
                "manufacturer": trait.manufacturer.value if trait.HasField("manufacturer") else None,
                "model": trait.model_name.value if trait.HasField("model_name") else None,
            }
        
        # BatteryPowerSourceTrait
        elif "BatteryPowerSourceTrait" in type_url:
            trait = power_pb2.BatteryPowerSourceTrait()
            property_any.Unpack(trait)
            result["decoded"] = True
            result["data"] = {
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
            result["decoded"] = True
            result["data"] = {
                "locked_state": trait.lockedState,
                "actuator_state": trait.actuatorState,
                "originator": trait.boltLockActor.originator.resourceId if trait.HasField("boltLockActor") and trait.boltLockActor.HasField("originator") else None,
            }
        
        # StructureInfoTrait
        elif "StructureInfoTrait" in type_url:
            trait = structure_pb2.StructureInfoTrait()
            property_any.Unpack(trait)
            result["decoded"] = True
            result["data"] = {
                "legacy_id": trait.legacy_id if trait.legacy_id else None,
                "ssid": trait.ssid if trait.ssid else None,
            }
        
        # UserInfoTrait
        elif "UserInfoTrait" in type_url:
            trait = user_pb2.UserInfoTrait()
            property_any.Unpack(trait)
            result["decoded"] = True
            result["data"] = {"user_id": "extracted_from_obj_id"}
    
    except Exception as e:
        result["error"] = str(e)
    
    return result


def decode_message(message: bytes) -> Dict[str, Any]:
    """Decode a single protobuf message and extract all traits."""
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
                
                type_url = property_any.type_url or ""
                if not type_url:
                    if hasattr(get_op, "data") and 7 in get_op.data:
                        type_url = "weave.trait.security.BoltLockTrait"
                    else:
                        continue
                
                trait_key = f"{obj_id}:{type_url}"
                decoded = decode_trait(property_any, type_url)
                
                all_traits[trait_key] = {
                    "object_id": obj_id,
                    "type_url": type_url,
                    **decoded,
                }
    
    except Exception as e:
        return {"error": str(e)}
    
    return {"traits": all_traits}


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Decode all messages from raw.bin file")
    parser.add_argument("file", type=Path, help="Raw.bin file to decode")
    
    args = parser.parse_args()
    
    if not args.file.exists():
        print(f"Error: File not found: {args.file}")
        return 1
    
    print("="*80)
    print("DECODING ALL MESSAGES")
    print("="*80)
    print(f"File: {args.file.name}\n")
    
    with open(args.file, "rb") as f:
        raw_data = f.read()
    
    print(f"Raw data: {len(raw_data)} bytes\n")
    
    # Extract all messages
    messages = extract_all_messages(raw_data)
    print(f"Extracted {len(messages)} message(s)\n")
    
    all_traits_found = {}
    decoded_count = 0
    failed_count = 0
    
    for i, message in enumerate(messages, 1):
        print(f"{'='*80}")
        print(f"Message {i}: {len(message)} bytes")
        print(f"{'='*80}\n")
        
        result = decode_message(message)
        
        if "error" in result:
            print(f"❌ Error: {result['error']}\n")
            failed_count += 1
            continue
        
        traits = result.get("traits", {})
        
        if not traits:
            print("⚠️  No traits found\n")
            continue
        
        print(f"Found {len(traits)} trait(s):\n")
        
        for trait_key, trait_info in sorted(traits.items()):
            type_url = trait_info["type_url"]
            obj_id = trait_info["object_id"]
            
            # Track unique traits
            if type_url not in all_traits_found:
                all_traits_found[type_url] = []
            
            print(f"  {type_url}")
            print(f"    Object ID: {obj_id}")
            
            if trait_info.get("decoded"):
                decoded_count += 1
                print(f"    ✅ Decoded")
                for key, value in trait_info.get("data", {}).items():
                    if value is not None:
                        print(f"       {key}: {value}")
                        # Store in all_traits_found
                        if key not in all_traits_found[type_url]:
                            all_traits_found[type_url].append({key: value})
            elif "error" in trait_info:
                failed_count += 1
                print(f"    ❌ Error: {trait_info['error']}")
            else:
                print(f"    ⚠️  No decoder")
            print()
    
    # Final summary
    print(f"{'='*80}")
    print("FINAL SUMMARY")
    print(f"{'='*80}\n")
    print(f"Messages processed: {len(messages)}")
    print(f"Traits found: {len(all_traits_found)}")
    print(f"✅ Decoded: {decoded_count}")
    print(f"❌ Failed: {failed_count}")
    print()
    
    print("All traits found:")
    for trait_type in sorted(all_traits_found.keys()):
        print(f"  - {trait_type}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

