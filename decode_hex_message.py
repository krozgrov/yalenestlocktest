#!/usr/bin/env python3
"""
Decode a hex-encoded protobuf message from Nest integration logs.

Usage:
    python decode_hex_message.py "0a8c0c1a8601..."
"""

import sys
import binascii
import json
from pathlib import Path

# Try to import protobuf modules
try:
    from proto.nest import rpc_pb2 as rpc
    PROTO_AVAILABLE = True
except ImportError:
    PROTO_AVAILABLE = False
    rpc = None
    print("Warning: Proto modules not available. Will try blackbox decoding only.", file=sys.stderr)

try:
    import blackboxprotobuf as bbp
    BLACKBOX_AVAILABLE = True
except ImportError:
    BLACKBOX_AVAILABLE = False
    print("Warning: blackboxprotobuf not available. Install with: pip install blackboxprotobuf", file=sys.stderr)


def decode_hex_message(hex_string: str):
    """Decode a hex-encoded protobuf message."""
    # Remove whitespace
    hex_string = hex_string.replace(" ", "").replace("\n", "")
    
    # Convert hex to bytes
    try:
        raw_bytes = binascii.unhexlify(hex_string)
    except binascii.Error as e:
        print(f"Error: Invalid hex string: {e}", file=sys.stderr)
        return None
    
    print(f"Message length: {len(raw_bytes)} bytes")
    print("=" * 80)
    
    results = {}
    
    # Try structured decoding
    if PROTO_AVAILABLE and rpc:
        print("\n📋 STRUCTURED DECODING (using proto definitions):")
        print("-" * 80)
        try:
            stream_body = rpc.StreamBody()
            stream_body.ParseFromString(raw_bytes)
            
            print("✅ Successfully parsed StreamBody")
            print(f"   Messages: {len(stream_body.message)}")
            
            extracted_data = {
                "devices": [],
                "structure_id": None,
                "user_id": None,
            }
            
            for msg_idx, msg in enumerate(stream_body.message):
                print(f"\n   Message {msg_idx + 1}:")
                for get_op_idx, get_op in enumerate(msg.get):
                    obj_id = get_op.object.id if get_op.object.id else None
                    obj_key = get_op.object.key if get_op.object.key else "unknown"
                    
                    print(f"      GetOp {get_op_idx + 1}:")
                    print(f"         Object ID: {obj_id}")
                    print(f"         Object Key: {obj_key}")
                    
                    # Extract structure ID
                    if obj_id and obj_id.startswith("STRUCTURE_"):
                        structure_id = obj_id.replace("STRUCTURE_", "")
                        extracted_data["structure_id"] = structure_id
                        print(f"         ✅ Structure ID: {structure_id}")
                    
                    # Extract user ID
                    if obj_id and obj_id.startswith("USER_"):
                        user_id = obj_id.replace("USER_", "")
                        extracted_data["user_id"] = user_id
                        print(f"         ✅ User ID: {user_id}")
                    
                    # Extract device ID
                    if obj_id and obj_id.startswith("DEVICE_"):
                        extracted_data["devices"].append(obj_id)
                        print(f"         ✅ Device ID: {obj_id}")
                    
                    # Check property type
                    property_any = getattr(get_op.data, "property", None)
                    if property_any:
                        type_url = getattr(property_any, "type_url", None)
                        if type_url:
                            print(f"         Type URL: {type_url}")
                            
                            # Check for specific traits
                            if "BoltLockTrait" in type_url:
                                print(f"         🔒 BoltLockTrait detected")
                            if "StructureInfoTrait" in type_url:
                                print(f"         🏠 StructureInfoTrait detected")
                            if "UserInfoTrait" in type_url:
                                print(f"         👤 UserInfoTrait detected")
            
            results["structured"] = extracted_data
            print(f"\n   📊 Extracted Data:")
            print(f"      Structure ID: {extracted_data['structure_id']}")
            print(f"      User ID: {extracted_data['user_id']}")
            print(f"      Devices: {extracted_data['devices']}")
            
        except Exception as e:
            print(f"❌ Structured decoding failed: {e}")
            results["structured_error"] = str(e)
    
    # Try blackbox decoding
    if BLACKBOX_AVAILABLE:
        print("\n\n📦 BLACKBOX DECODING (using blackboxprotobuf):")
        print("-" * 80)
        try:
            message_json, typedef = bbp.protobuf_to_json(raw_bytes)
            
            if isinstance(message_json, str):
                message_data = json.loads(message_json)
            else:
                message_data = message_json
            
            print("✅ Successfully decoded with blackboxprotobuf")
            print(f"\n   Decoded structure (first 500 chars):")
            print(json.dumps(message_data, indent=2)[:500] + "...")
            
            # Extract IDs from blackbox data
            extracted_ids = {
                "structure_id": None,
                "user_id": None,
                "devices": [],
            }
            
            def find_ids(obj, path=""):
                if isinstance(obj, dict):
                    if "1" in obj and isinstance(obj["1"], str):
                        obj_id = obj["1"]
                        if obj_id.startswith("STRUCTURE_"):
                            extracted_ids["structure_id"] = obj_id.replace("STRUCTURE_", "")
                        elif obj_id.startswith("USER_"):
                            extracted_ids["user_id"] = obj_id.replace("USER_", "")
                        elif obj_id.startswith("DEVICE_"):
                            extracted_ids["devices"].append(obj_id)
                    
                    for key, value in obj.items():
                        find_ids(value, f"{path}.{key}" if path else key)
                elif isinstance(obj, list):
                    for item in obj:
                        find_ids(item, path)
            
            find_ids(message_data)
            
            results["blackbox"] = {
                "message": message_data,
                "extracted_ids": extracted_ids,
            }
            
            print(f"\n   📊 Extracted IDs from blackbox:")
            print(f"      Structure ID: {extracted_ids['structure_id']}")
            print(f"      User ID: {extracted_ids['user_id']}")
            print(f"      Devices: {extracted_ids['devices']}")
            
        except Exception as e:
            print(f"❌ Blackbox decoding failed: {e}")
            import traceback
            traceback.print_exc()
            results["blackbox_error"] = str(e)
    
    # Summary
    print("\n" + "=" * 80)
    print("📋 SUMMARY")
    print("=" * 80)
    
    structure_id = None
    user_id = None
    devices = []
    
    if results.get("structured"):
        structure_id = results["structured"]["structure_id"]
        user_id = results["structured"]["user_id"]
        devices = results["structured"]["devices"]
    
    if results.get("blackbox"):
        if not structure_id:
            structure_id = results["blackbox"]["extracted_ids"]["structure_id"]
        if not user_id:
            user_id = results["blackbox"]["extracted_ids"]["user_id"]
        if not devices:
            devices = results["blackbox"]["extracted_ids"]["devices"]
    
    print(f"\n✅ Structure ID: {structure_id or 'NOT FOUND'}")
    print(f"✅ User ID: {user_id or 'NOT FOUND'}")
    print(f"✅ Devices: {', '.join(devices) if devices else 'NOT FOUND'}")
    
    return results


def main():
    if len(sys.argv) < 2:
        print("Usage: python decode_hex_message.py <hex_string>")
        print("\nExample:")
        print('  python decode_hex_message.py "0a8c0c1a8601..."')
        return 1
    
    hex_string = sys.argv[1]
    decode_hex_message(hex_string)
    return 0


if __name__ == "__main__":
    sys.exit(main())

