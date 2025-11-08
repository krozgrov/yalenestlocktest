#!/usr/bin/env python3
"""
Test message decoding and show full output.
"""

import sys
from pathlib import Path
import json

# Add current directory to path
sys.path.insert(0, '.')

try:
    from proto.nest import rpc_pb2 as rpc
    from proto.weave.trait import security_pb2 as weave_security
    from proto.nest.trait import structure_pb2 as nest_structure
    from proto.nest.trait import user_pb2 as nest_user
    PROTO_AVAILABLE = True
except ImportError as e:
    print(f"Error importing proto files: {e}")
    PROTO_AVAILABLE = False
    sys.exit(1)


def decode_message(raw_bytes: bytes):
    """Decode a protobuf message and return structured data."""
    result = {
        "success": False,
        "messages": [],
        "errors": [],
    }
    
    try:
        stream_body = rpc.StreamBody()
        stream_body.ParseFromString(raw_bytes)
        
        result["success"] = True
        result["message_count"] = len(stream_body.message)
        
        for msg_idx, msg in enumerate(stream_body.message):
            msg_data = {
                "index": msg_idx,
                "get_ops": [],
                "set_ops": len(msg.set),
            }
            
            for get_op in msg.get:
                op_data = {
                    "object_id": get_op.object.id if get_op.object.id else None,
                    "object_key": get_op.object.key if get_op.object.key else None,
                    "trait_data": None,
                }
                
                # Try to extract property
                if hasattr(get_op.data, "property") and get_op.data.property:
                    prop = get_op.data.property
                    op_data["type_url"] = prop.type_url
                    
                    # Try to unpack based on type
                    try:
                        if "BoltLockTrait" in prop.type_url:
                            bolt_lock = weave_security.BoltLockTrait()
                            if prop.Unpack(bolt_lock):
                                op_data["trait_data"] = {
                                    "type": "BoltLockTrait",
                                    "locked_state": bolt_lock.lockedState,
                                    "actuator_state": bolt_lock.actuatorState,
                                    "bolt_state": getattr(bolt_lock, "boltState", None),
                                }
                        elif "StructureInfoTrait" in prop.type_url:
                            structure = nest_structure.StructureInfoTrait()
                            if prop.Unpack(structure):
                                op_data["trait_data"] = {
                                    "type": "StructureInfoTrait",
                                    "legacy_id": structure.legacy_id if hasattr(structure, "legacy_id") else None,
                                }
                        elif "UserInfoTrait" in prop.type_url:
                            user = nest_user.UserInfoTrait()
                            if prop.Unpack(user):
                                op_data["trait_data"] = {
                                    "type": "UserInfoTrait",
                                }
                    except Exception as e:
                        op_data["unpack_error"] = str(e)[:100]
                
                msg_data["get_ops"].append(op_data)
            
            result["messages"].append(msg_data)
    
    except Exception as e:
        result["errors"].append(str(e))
        import traceback
        result["traceback"] = traceback.format_exc()
    
    return result


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
    print("MESSAGE DECODING TEST - FULL OUTPUT")
    print("="*80)
    print(f"Capture: {latest_capture.name}")
    print()
    
    for raw_file in raw_files[:2]:  # Test first 2
        print("="*80)
        print(f"Testing: {raw_file.name}")
        print("="*80)
        print()
        
        with open(raw_file, "rb") as f:
            raw_bytes = f.read()
        
        print(f"Message size: {len(raw_bytes)} bytes")
        print()
        
        result = decode_message(raw_bytes)
        
        if result["success"]:
            print("✅ DECODING SUCCESSFUL!")
            print()
            print(f"Messages decoded: {result['message_count']}")
            print()
            
            for msg in result["messages"]:
                print(f"Message {msg['index'] + 1}:")
                print(f"  GetOps: {len(msg['get_ops'])}")
                print(f"  SetOps: {msg['set_ops']}")
                print()
                
                for op_idx, op in enumerate(msg["get_ops"]):
                    print(f"  GetOp {op_idx + 1}:")
                    print(f"    Object ID: {op['object_id']}")
                    print(f"    Object Key: {op['object_key']}")
                    
                    if op.get("type_url"):
                        print(f"    Type URL: {op['type_url']}")
                    
                    if op.get("trait_data"):
                        trait = op["trait_data"]
                        print(f"    ✅ Trait Data Extracted:")
                        print(f"       Type: {trait['type']}")
                        for key, value in trait.items():
                            if key != "type":
                                print(f"       {key}: {value}")
                    elif op.get("unpack_error"):
                        print(f"    ⚠️  Unpack error: {op['unpack_error']}")
                    else:
                        print(f"    ℹ️  No trait data extracted")
                    print()
        else:
            print("❌ DECODING FAILED")
            for error in result.get("errors", []):
                print(f"  Error: {error}")
            if "traceback" in result:
                print("\nTraceback:")
                print(result["traceback"])
        
        print()
    
    print("="*80)
    print("DECODING TEST COMPLETE")
    print("="*80)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

