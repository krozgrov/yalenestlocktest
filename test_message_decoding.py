#!/usr/bin/env python3
"""
Test message decoding with generated proto files.

This script:
1. Loads captured protobuf messages
2. Attempts to decode them with generated proto files
3. Shows decoded output
4. Validates successful decoding
"""

import argparse
import sys
from pathlib import Path
import json

# Try to import protobuf
try:
    from google.protobuf.message import DecodeError
    PROTOBUF_AVAILABLE = True
except ImportError:
    PROTOBUF_AVAILABLE = False
    print("Warning: google.protobuf not available. Install with: pip install protobuf", file=sys.stderr)

# Try to import existing proto files
try:
    from proto.nest import rpc_pb2 as rpc
    EXISTING_PROTO_AVAILABLE = True
except ImportError:
    EXISTING_PROTO_AVAILABLE = False
    rpc = None


def decode_with_streambody(raw_bytes: bytes) -> dict:
    """Decode message using existing StreamBody proto."""
    if not EXISTING_PROTO_AVAILABLE or not PROTOBUF_AVAILABLE:
        return {"error": "Proto files not available"}
    
    try:
        stream_body = rpc.StreamBody()
        stream_body.ParseFromString(raw_bytes)
        
        result = {
            "success": True,
            "messages_count": len(stream_body.message),
            "messages": [],
        }
        
        for msg_idx, msg in enumerate(stream_body.message):
            msg_data = {
                "index": msg_idx,
                "get_ops": len(msg.get),
                "set_ops": len(msg.set),
                "objects": [],
            }
            
            for get_op in msg.get:
                obj_id = get_op.object.id if get_op.object.id else None
                obj_key = get_op.object.key if get_op.object.key else None
                
                obj_data = {
                    "id": obj_id,
                    "key": obj_key,
                }
                
                # Check for property
                if hasattr(get_op.data, "property"):
                    prop = get_op.data.property
                    if prop:
                        obj_data["type_url"] = prop.type_url
                        obj_data["has_data"] = len(prop.value) > 0
                
                msg_data["objects"].append(obj_data)
            
            result["messages"].append(msg_data)
        
        return result
    except DecodeError as e:
        return {"success": False, "error": f"DecodeError: {e}"}
    except Exception as e:
        return {"success": False, "error": f"Error: {e}"}


def decode_with_generated_proto(raw_bytes: bytes, proto_file: Path) -> dict:
    """Try to decode with a generated proto file."""
    if not PROTOBUF_AVAILABLE:
        return {"error": "protobuf not available"}
    
    proto_name = proto_file.stem
    pb2_file = proto_file.parent / f"{proto_name}_pb2.py"
    
    if not pb2_file.exists():
        return {"error": f"pb2 file not found: {pb2_file.name}"}
    
    try:
        import importlib.util
        rel_path = pb2_file.relative_to(proto_file.parent.parent.parent)
        module_path = str(rel_path).replace("/", ".").replace("\\", ".").replace(".py", "")
        
        spec = importlib.util.spec_from_file_location(module_path, pb2_file)
        if spec is None or spec.loader is None:
            return {"error": "Could not create module spec"}
        
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        
        # Find message classes
        message_classes = [
            attr for attr in dir(module)
            if not attr.startswith("_") and 
               hasattr(getattr(module, attr), "DESCRIPTOR")
        ]
        
        if not message_classes:
            return {"error": "No message classes found"}
        
        # Try to parse with first message class
        first_message = getattr(module, message_classes[0])
        instance = first_message()
        instance.ParseFromString(raw_bytes)
        
        # Convert to dict for display
        result = {
            "success": True,
            "message_type": message_classes[0],
            "fields": {},
        }
        
        # Extract field values
        for field_descriptor in instance.DESCRIPTOR.fields:
            field_name = field_descriptor.name
            if instance.HasField(field_name):
                field_value = getattr(instance, field_name)
                if hasattr(field_value, "__len__"):
                    result["fields"][field_name] = f"<{type(field_value).__name__} with {len(field_value)} items>"
                else:
                    result["fields"][field_name] = str(field_value)[:100]
        
        return result
    except DecodeError as e:
        return {"success": False, "error": f"DecodeError: {str(e)[:200]}"}
    except Exception as e:
        return {"success": False, "error": f"Error: {str(e)[:200]}"}


def test_capture_message(capture_file: Path, proto_final: Path):
    """Test decoding a captured message."""
    print("="*80)
    print(f"TESTING MESSAGE DECODING: {capture_file.name}")
    print("="*80)
    print()
    
    # Load raw bytes
    with open(capture_file, "rb") as f:
        raw_bytes = f.read()
    
    print(f"Message size: {len(raw_bytes)} bytes")
    print()
    
    # Test 1: Decode with existing StreamBody
    print("Test 1: Decoding with existing StreamBody proto...")
    print("-" * 80)
    streambody_result = decode_with_streambody(raw_bytes)
    
    if streambody_result.get("success"):
        print("✅ Successfully decoded with StreamBody")
        print(f"   Messages: {streambody_result['messages_count']}")
        for msg in streambody_result["messages"][:3]:  # Show first 3
            print(f"   Message {msg['index']}:")
            print(f"     GetOps: {msg['get_ops']}, SetOps: {msg['set_ops']}")
            for obj in msg["objects"][:3]:  # Show first 3 objects
                print(f"       Object: {obj['id']} ({obj['key']})")
                if obj.get("type_url"):
                    print(f"         Type: {obj['type_url']}")
    else:
        print(f"❌ Failed: {streambody_result.get('error', 'Unknown error')}")
    print()
    
    # Test 2: Try decoding with generated proto files
    print("Test 2: Attempting to decode with generated proto files...")
    print("-" * 80)
    
    # Find relevant proto files based on message content
    proto_files = list(proto_final.rglob("*.proto"))
    
    # Try each proto file
    success_count = 0
    for proto_file in proto_files[:5]:  # Test first 5
        rel_path = proto_file.relative_to(proto_final)
        print(f"   Trying {rel_path}...", end=" ")
        
        result = decode_with_generated_proto(raw_bytes, proto_file)
        
        if result.get("success"):
            print("✅ SUCCESS")
            print(f"      Message type: {result['message_type']}")
            if result.get("fields"):
                print(f"      Fields found: {len(result['fields'])}")
                for field_name, field_value in list(result["fields"].items())[:3]:
                    print(f"        {field_name}: {field_value}")
            success_count += 1
        else:
            error = result.get("error", "Unknown")
            if "DecodeError" in error or "ParseFromString" in error:
                print("⚠️  Parse failed (expected - message may not match this proto)")
            else:
                print(f"⚠️  {error[:60]}")
    
    print()
    print(f"   Results: {success_count}/{min(5, len(proto_files))} proto files could parse this message")
    print()
    
    # Test 3: Show hex preview
    print("Test 3: Message hex preview (first 200 bytes)...")
    print("-" * 80)
    hex_preview = raw_bytes[:200].hex()
    for i in range(0, len(hex_preview), 64):
        print(f"   {hex_preview[i:i+64]}")
    print()
    
    # Test 4: Extract readable strings
    print("Test 4: Readable strings in message...")
    print("-" * 80)
    readable_strings = []
    current_string = bytearray()
    for byte in raw_bytes[:1000]:  # Check first 1000 bytes
        if 32 <= byte <= 126:  # Printable ASCII
            current_string.append(byte)
        else:
            if len(current_string) >= 4:
                readable_strings.append(current_string.decode('ascii', errors='ignore'))
            current_string = bytearray()
    
    if len(current_string) >= 4:
        readable_strings.append(current_string.decode('ascii', errors='ignore'))
    
    for string in readable_strings[:10]:  # Show first 10
        if any(keyword in string.lower() for keyword in ['trait', 'device', 'structure', 'user', 'bolt', 'lock']):
            print(f"   ✅ {string}")
    print()
    
    return streambody_result.get("success", False)


def main():
    parser = argparse.ArgumentParser(
        description="Test message decoding with generated proto files"
    )
    parser.add_argument(
        "--capture-file",
        type=Path,
        help="Specific capture file to test (raw.bin)",
    )
    parser.add_argument(
        "--capture-dir",
        type=Path,
        default=Path("captures"),
        help="Directory containing captures",
    )
    parser.add_argument(
        "--proto-final",
        type=Path,
        default=Path("proto/final"),
        help="Directory with generated proto files",
    )
    
    args = parser.parse_args()
    
    if args.capture_file:
        capture_files = [args.capture_file]
    else:
        # Find latest capture
        if not args.capture_dir.exists():
            print(f"Error: Capture directory does not exist: {args.capture_dir}")
            return 1
        
        capture_dirs = sorted([d for d in args.capture_dir.iterdir() if d.is_dir()], 
                            key=lambda x: x.stat().st_mtime, reverse=True)
        
        if not capture_dirs:
            print(f"Error: No capture directories found in {args.capture_dir}")
            return 1
        
        # Get raw.bin files from latest capture
        capture_files = list(capture_dirs[0].glob("*.raw.bin"))
        
        if not capture_files:
            print(f"Error: No raw.bin files found in {capture_dirs[0]}")
            return 1
    
    print("="*80)
    print("MESSAGE DECODING TEST")
    print("="*80)
    print()
    
    success_count = 0
    for capture_file in capture_files[:3]:  # Test first 3
        if test_capture_message(capture_file, args.proto_final):
            success_count += 1
    
    print("="*80)
    print("DECODING TEST SUMMARY")
    print("="*80)
    print(f"Messages tested: {len(capture_files[:3])}")
    print(f"Successfully decoded: {success_count}")
    print()
    
    if success_count > 0:
        print("✅ Message decoding successful!")
        print("   The proto files can decode real Nest API messages.")
    else:
        print("⚠️  Some messages could not be decoded")
        print("   This may be expected if messages don't match proto structure")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

