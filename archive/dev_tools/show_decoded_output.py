#!/usr/bin/env python3
"""
Show decoded message output using blackboxprotobuf and existing proto files.
"""

import sys
import json
from pathlib import Path

sys.path.insert(0, '.')

# Try to use blackboxprotobuf
try:
    import blackboxprotobuf as bbp
    BLACKBOX_AVAILABLE = True
except ImportError:
    BLACKBOX_AVAILABLE = False
    print("Warning: blackboxprotobuf not available", file=sys.stderr)

# Try existing proto files
try:
    from proto.nest import rpc_pb2 as rpc
    from proto.weave.trait import security_pb2 as weave_security
    from proto.nest.trait import structure_pb2 as nest_structure
    PROTO_AVAILABLE = True
except ImportError:
    PROTO_AVAILABLE = False
    print("Warning: Proto files not available", file=sys.stderr)


def show_decoded_message(capture_file: Path):
    """Show decoded message output."""
    print("="*80)
    print(f"DECODING: {capture_file.name}")
    print("="*80)
    print()
    
    with open(capture_file, "rb") as f:
        raw_bytes = f.read()
    
    print(f"Message size: {len(raw_bytes)} bytes")
    print()
    
    # Method 1: Blackbox decoding
    if BLACKBOX_AVAILABLE:
        print("Method 1: Blackboxprotobuf Decoding")
        print("-" * 80)
        try:
            message_json, typedef = bbp.protobuf_to_json(raw_bytes)
            
            if isinstance(message_json, str):
                data = json.loads(message_json)
            else:
                data = message_json
            
            print("✅ Successfully decoded with blackboxprotobuf!")
            print()
            
            # Extract key information
            print("Extracted Information:")
            print()
            
            # Find structure ID
            def find_structure_id(obj, path=""):
                if isinstance(obj, dict):
                    if "1" in obj and isinstance(obj["1"], str) and obj["1"].startswith("STRUCTURE_"):
                        return obj["1"].replace("STRUCTURE_", "")
                    for key, value in obj.items():
                        result = find_structure_id(value, f"{path}.{key}")
                        if result:
                            return result
                elif isinstance(obj, list):
                    for item in obj:
                        result = find_structure_id(item, path)
                        if result:
                            return result
                return None
            
            # Find user ID
            def find_user_id(obj, path=""):
                if isinstance(obj, dict):
                    if "1" in obj and isinstance(obj["1"], str) and obj["1"].startswith("USER_"):
                        return obj["1"].replace("USER_", "")
                    for key, value in obj.items():
                        result = find_user_id(value, f"{path}.{key}")
                        if result:
                            return result
                elif isinstance(obj, list):
                    for item in obj:
                        result = find_user_id(item, path)
                        if result:
                            return result
                return None
            
            # Find device IDs
            def find_device_ids(obj, path=""):
                devices = []
                if isinstance(obj, dict):
                    if "1" in obj and isinstance(obj["1"], str) and obj["1"].startswith("DEVICE_"):
                        devices.append(obj["1"])
                    for key, value in obj.items():
                        devices.extend(find_device_ids(value, f"{path}.{key}"))
                elif isinstance(obj, list):
                    for item in obj:
                        devices.extend(find_device_ids(item, path))
                return devices
            
            structure_id = find_structure_id(data)
            user_id = find_user_id(data)
            device_ids = find_device_ids(data)
            
            if structure_id:
                print(f"  ✅ Structure ID: {structure_id}")
            if user_id:
                print(f"  ✅ User ID: {user_id}")
            if device_ids:
                print(f"  ✅ Device IDs: {', '.join(set(device_ids))}")
            
            print()
            print("Full decoded structure (first 1500 chars):")
            print(json.dumps(data, indent=2)[:1500])
            print("... (truncated)")
            print()
            
        except Exception as e:
            print(f"❌ Blackbox decoding failed: {e}")
            import traceback
            traceback.print_exc()
            print()
    
    # Method 2: Try existing proto (may fail due to incomplete definitions)
    if PROTO_AVAILABLE:
        print("Method 2: Existing Proto Decoding")
        print("-" * 80)
        try:
            stream_body = rpc.StreamBody()
            stream_body.ParseFromString(raw_bytes)
            
            print("✅ Successfully decoded with existing proto!")
            print(f"Messages: {len(stream_body.message)}")
            print()
            
            for msg_idx, msg in enumerate(stream_body.message):
                print(f"Message {msg_idx + 1}:")
                print(f"  GetOps: {len(msg.get)}")
                
                for get_op in msg.get[:3]:
                    obj_id = get_op.object.id if get_op.object.id else None
                    obj_key = get_op.object.key if get_op.object.key else None
                    print(f"    Object: {obj_id} ({obj_key})")
                    
                    if hasattr(get_op.data, "property") and get_op.data.property:
                        prop = get_op.data.property
                        print(f"      Type: {prop.type_url}")
                        
                        if "BoltLockTrait" in prop.type_url:
                            try:
                                bolt_lock = weave_security.BoltLockTrait()
                                if prop.Unpack(bolt_lock):
                                    print(f"      ✅ Unpacked BoltLockTrait")
                                    print(f"         Locked: {bolt_lock.lockedState}")
                            except:
                                pass
                print()
                
        except Exception as e:
            print(f"⚠️  Existing proto decode failed (expected): {e}")
            print("   This is why we need the updated proto files!")
            print()
    
    # Method 3: Show hex and readable strings
    print("Method 3: Raw Message Analysis")
    print("-" * 80)
    
    # Hex preview
    print("Hex preview (first 100 bytes):")
    hex_str = raw_bytes[:100].hex()
    for i in range(0, len(hex_str), 32):
        print(f"  {hex_str[i:i+32]}")
    print()
    
    # Readable strings
    print("Readable strings found:")
    current_string = bytearray()
    strings_found = []
    for byte in raw_bytes[:500]:
        if 32 <= byte <= 126:
            current_string.append(byte)
        else:
            if len(current_string) >= 4:
                strings_found.append(current_string.decode('ascii', errors='ignore'))
            current_string = bytearray()
    
    for string in strings_found[:15]:
        if any(kw in string.lower() for kw in ['trait', 'device', 'structure', 'user', 'bolt', 'lock', 'yale']):
            print(f"  ✅ {string}")
    print()


def main():
    # Find latest capture
    captures_dir = Path("captures")
    if not captures_dir.exists():
        print("Error: captures directory not found")
        return 1
    
    capture_dirs = sorted([d for d in captures_dir.iterdir() if d.is_dir()], 
                         key=lambda x: x.stat().st_mtime, reverse=True)
    
    if not capture_dirs:
        print("Error: No capture directories found")
        return 1
    
    latest_capture = capture_dirs[0]
    raw_files = sorted(latest_capture.glob("*.raw.bin"))
    
    if not raw_files:
        print(f"Error: No raw.bin files in {latest_capture}")
        return 1
    
    print("="*80)
    print("MESSAGE DECODING OUTPUT")
    print("="*80)
    print(f"Capture: {latest_capture.name}")
    print()
    
    for raw_file in raw_files[:2]:  # Show first 2
        show_decoded_message(raw_file)
        print()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

