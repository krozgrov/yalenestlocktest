#!/usr/bin/env python3
"""
Final comprehensive test - decode all traits from captured messages.

This uses the actual message processing flow and extracts all trait data.
"""

import sys
import json
import asyncio
from pathlib import Path
from typing import Dict, Any, List

# Import handler and proto modules
from protobuf_handler import NestProtobufHandler
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
        
        # BoltLockTrait (main one, not settings/capabilities)
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
            result["data"] = {"decoded": True}  # Add specific fields as needed
            result["decoded"] = True
    
    except Exception as e:
        result["error"] = str(e)
    
    return result


async def process_file_with_handler(capture_file: Path) -> Dict[str, Any]:
    """Process file using handler and extract all traits."""
    handler = NestProtobufHandler()
    
    try:
        with open(capture_file, "rb") as f:
            raw_data = f.read()
        
        # Use handler's ingest_chunk to process (handles gRPC-web format)
        results = await handler._ingest_chunk(raw_data)
        
        # Also extract traits from stream_body
        all_traits = {}
        
        try:
            from proto.nest import rpc_pb2
            stream_body = handler.stream_body
            
            for msg in stream_body.message:
                for get_op in msg.get:
                    obj_id = get_op.object.id if get_op.object.id else None
                    property_any = getattr(get_op.data, "property", None)
                    
                    if property_any:
                        type_url = property_any.type_url or ""
                        if not type_url and hasattr(get_op, "data") and 7 in get_op.data:
                            type_url = "weave.trait.security.BoltLockTrait"
                        
                        if type_url:
                            decoded = decode_trait(property_any, type_url)
                            trait_key = f"{obj_id}:{type_url}"
                            all_traits[trait_key] = {
                                "object_id": obj_id,
                                "type_url": type_url,
                                **decoded,
                            }
        except Exception as e:
            pass  # Ignore extraction errors
        
        return {
            "file": capture_file.name,
            "handler_results": results,
            "traits": all_traits,
            "success": True,
        }
    
    except Exception as e:
        return {
            "file": capture_file.name,
            "error": str(e),
            "success": False,
        }


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Final comprehensive trait decoding test"
    )
    parser.add_argument(
        "--capture-dir",
        type=Path,
        help="Capture directory to test",
    )
    
    args = parser.parse_args()
    
    if args.capture_dir:
        capture_dir = args.capture_dir
    else:
        # Use latest
        captures_dir = Path("captures")
        if not captures_dir.exists():
            print("Error: captures directory does not exist")
            return 1
        
        capture_dirs = sorted([d for d in captures_dir.iterdir() if d.is_dir()],
                            key=lambda x: x.stat().st_mtime, reverse=True)
        if not capture_dirs:
            print("Error: No capture directories found")
            return 1
        capture_dir = capture_dirs[0]
    
    print("="*80)
    print("FINAL COMPREHENSIVE TRAIT DECODING TEST")
    print("="*80)
    print(f"Capture: {capture_dir.name}\n")
    
    raw_files = sorted(capture_dir.glob("*.raw.bin"))
    
    if not raw_files:
        print("⚠️  No raw.bin files found")
        return 1
    
    all_traits_found = set()
    all_traits_decoded = set()
    all_traits_failed = set()
    
    for raw_file in raw_files:
        result = asyncio.run(process_file_with_handler(raw_file))
        
        print(f"\nFile: {result['file']}")
        
        if result["success"]:
            print("  ✅ Processed successfully")
            
            # Show handler results
            handler_results = result.get("handler_results", [])
            if handler_results:
                for hr in handler_results:
                    if hr.get("yale"):
                        print("  Lock data:")
                        for device_id, device_data in hr["yale"].items():
                            print(f"    Device: {device_id}")
                            for key, value in device_data.items():
                                print(f"      {key}: {value}")
            
            # Show decoded traits
            traits = result.get("traits", {})
            if traits:
                print(f"  Decoded traits ({len(traits)}):")
                for trait_key, trait_info in sorted(traits.items()):
                    type_url = trait_info["type_url"]
                    all_traits_found.add(type_url)
                    
                    if trait_info.get("decoded"):
                        all_traits_decoded.add(type_url)
                        print(f"    ✅ {type_url}")
                        for key, value in trait_info.get("data", {}).items():
                            if value is not None:
                                print(f"       {key}: {value}")
                    elif "error" in trait_info:
                        all_traits_failed.add(type_url)
                        print(f"    ❌ {type_url}: {trait_info['error']}")
                    else:
                        print(f"    ⚠️  {type_url}: Not decoded")
            else:
                print("  ⚠️  No traits extracted")
        else:
            print(f"  ❌ Error: {result.get('error', 'Unknown')}")
    
    # Final summary
    print(f"\n{'='*80}")
    print("FINAL SUMMARY")
    print(f"{'='*80}\n")
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
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

