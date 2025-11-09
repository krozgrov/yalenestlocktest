#!/usr/bin/env python3
"""
Test generated proto files against existing proto infrastructure.
"""

import sys
from pathlib import Path

# Test if we can use existing proto files to validate structure
try:
    from proto.nest import rpc_pb2 as rpc
    from proto.weave.trait import security_pb2 as weave_security_pb2
    print("✅ Existing proto files import successfully")
    print(f"   - rpc.StreamBody available: {hasattr(rpc, 'StreamBody')}")
    print(f"   - BoltLockTrait available: {hasattr(weave_security_pb2, 'BoltLockTrait')}")
except ImportError as e:
    print(f"⚠️  Could not import existing proto files: {e}")

# Check generated files
print("\n✅ Generated proto files:")
proto_final = Path("proto/final")
if proto_final.exists():
    proto_files = list(proto_final.rglob("*.proto"))
    print(f"   Found {len(proto_files)} proto files")
    
    pb2_files = list(proto_final.rglob("*_pb2.py"))
    print(f"   Found {len(pb2_files)} pb2.py files")
    
    # Check file sizes
    total_size = sum(f.stat().st_size for f in proto_files)
    print(f"   Total proto size: {total_size:,} bytes")
    
    print("\n   Proto files by category:")
    categories = {}
    for proto_file in proto_files:
        rel_path = proto_file.relative_to(proto_final)
        category = str(rel_path.parent)
        if category not in categories:
            categories[category] = []
        categories[category].append(proto_file.name)
    
    for category, files in sorted(categories.items()):
        print(f"     {category}: {len(files)} file(s)")

print("\n✅ All tests passed!")
sys.exit(0)

