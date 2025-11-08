#!/usr/bin/env python3
"""
Generate and compile all proto files for Home Assistant integration.

This script:
1. Collects all proto files from yalenestlocktest
2. Copies/updates them to HA integration directory
3. Compiles them to pb2.py files using protoc
4. Ensures proper structure and imports
"""

import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Dict


# Paths
YALENEST_ROOT = Path(__file__).parent
HA_INTEGRATION_ROOT = Path(__file__).parent.parent / "ha-nest-yale-integration"
HA_PROTO_DIR = HA_INTEGRATION_ROOT / "custom_components" / "nest_yale_lock" / "proto"
YALENEST_PROTO_DIR = YALENEST_ROOT / "proto"

# Proto file mappings: (source_path, destination_path_in_ha)
PROTO_MAPPINGS = [
    # Weave common
    ("weave/common.proto", "weave/common.proto"),
    
    # Weave traits
    ("weave/trait/description.proto", "weave/trait/description.proto"),
    ("weave/trait/power.proto", "weave/trait/power.proto"),
    ("weave/trait/security.proto", "weave/trait/security.proto"),
    ("weave/trait/heartbeat.proto", "weave/trait/heartbeat.proto"),
    ("weave/trait/peerdevices.proto", "weave/trait/peerdevices.proto"),
    
    # Nest RPC
    ("nest/rpc.proto", "nest/rpc.proto"),
    
    # Nest traits
    ("nest/trait/structure.proto", "nest/trait/structure.proto"),
    ("nest/trait/user.proto", "nest/trait/user.proto"),
    ("nest/trait/security.proto", "nest/trait/security.proto"),
    ("nest/trait/hvac.proto", "nest/trait/hvac.proto"),
    ("nest/trait/sensor.proto", "nest/trait/sensor.proto"),
    ("nest/trait/detector.proto", "nest/trait/detector.proto"),
    ("nest/trait/located.proto", "nest/trait/located.proto"),
    ("nest/trait/occupancy.proto", "nest/trait/occupancy.proto"),
    
    # Nest messages and interfaces
    ("nest/messages.proto", "nest/messages.proto"),
    ("nest/iface.proto", "nest/iface.proto"),
    
    # Gateway
    ("nestlabs/gateway/v1.proto", "nestlabs/gateway/v1.proto"),
    ("nestlabs/gateway/v2.proto", "nestlabs/gateway/v2.proto"),
]


def find_proto_file(relative_path: str, search_dirs: List[Path]) -> Path | None:
    """Find a proto file in multiple search directories."""
    for search_dir in search_dirs:
        proto_path = search_dir / relative_path
        if proto_path.exists():
            return proto_path
    return None


def copy_proto_files():
    """Copy proto files from yalenestlocktest to HA integration."""
    print("="*80)
    print("COPYING PROTO FILES")
    print("="*80)
    print()
    
    copied = []
    missing = []
    
    for source_rel, dest_rel in PROTO_MAPPINGS:
        source_path = find_proto_file(source_rel, [YALENEST_PROTO_DIR])
        
        if not source_path:
            # Try in updated/ subdirectory
            source_path = find_proto_file(source_rel, [YALENEST_PROTO_DIR / "updated"])
        
        if not source_path:
            missing.append((source_rel, dest_rel))
            continue
        
        dest_path = HA_PROTO_DIR / dest_rel
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Copy file
        shutil.copy2(source_path, dest_path)
        copied.append((source_rel, dest_rel))
        print(f"✅ Copied: {source_rel} -> {dest_rel}")
    
    print()
    if missing:
        print(f"⚠️  {len(missing)} proto file(s) not found:")
        for source_rel, dest_rel in missing:
            print(f"   - {source_rel}")
    print()
    print(f"✅ Copied {len(copied)} proto file(s)")
    return len(copied) > 0


def compile_proto_files():
    """Compile proto files to pb2.py using protoc."""
    print("="*80)
    print("COMPILING PROTO FILES")
    print("="*80)
    print()
    
    # Find protoc
    protoc_path = shutil.which("protoc")
    if not protoc_path:
        print("❌ Error: protoc not found in PATH")
        print("   Install with: brew install protobuf (macOS) or apt-get install protobuf-compiler (Linux)")
        return False
    
    print(f"Using protoc: {protoc_path}")
    print()
    
    # Get all proto files
    proto_files = list(HA_PROTO_DIR.rglob("*.proto"))
    
    if not proto_files:
        print("❌ No proto files found to compile")
        return False
    
    # Compile each proto file
    compiled = []
    failed = []
    
    for proto_file in sorted(proto_files):
        try:
            # Calculate relative path from proto directory
            rel_path = proto_file.relative_to(HA_PROTO_DIR)
            output_dir = proto_file.parent
            
            # Build protoc command
            cmd = [
                protoc_path,
                f"--python_out={HA_PROTO_DIR}",
                f"--proto_path={HA_PROTO_DIR}",
                str(rel_path),
            ]
            
            print(f"Compiling: {rel_path}")
            result = subprocess.run(
                cmd,
                cwd=HA_PROTO_DIR,
                capture_output=True,
                text=True,
            )
            
            if result.returncode == 0:
                compiled.append(rel_path)
                print(f"  ✅ Generated: {output_dir / proto_file.stem}_pb2.py")
            else:
                failed.append((rel_path, result.stderr))
                print(f"  ❌ Failed: {result.stderr[:200]}")
        
        except Exception as e:
            failed.append((rel_path, str(e)))
            print(f"  ❌ Error: {e}")
    
    print()
    print(f"✅ Compiled {len(compiled)} proto file(s)")
    if failed:
        print(f"⚠️  {len(failed)} proto file(s) failed to compile")
    
    return len(compiled) > 0


def verify_pb2_files():
    """Verify that pb2 files can be imported."""
    print("="*80)
    print("VERIFYING PB2 FILES")
    print("="*80)
    print()
    
    # Find all pb2 files
    pb2_files = list(HA_PROTO_DIR.rglob("*_pb2.py"))
    
    if not pb2_files:
        print("⚠️  No pb2 files found")
        return False
    
    imported = []
    failed = []
    
    for pb2_file in sorted(pb2_files):
        try:
            # Calculate import path
            rel_path = pb2_file.relative_to(HA_PROTO_DIR)
            import_path = str(rel_path.with_suffix("")).replace("/", ".")
            
            # Try to import
            import importlib
            module = importlib.import_module(f"custom_components.nest_yale_lock.proto.{import_path}")
            
            imported.append(import_path)
            print(f"✅ {import_path}")
        
        except Exception as e:
            failed.append((import_path, str(e)))
            print(f"❌ {import_path}: {e}")
    
    print()
    print(f"✅ {len(imported)} pb2 file(s) can be imported")
    if failed:
        print(f"⚠️  {len(failed)} pb2 file(s) failed to import")
    
    return len(imported) > 0


def main():
    """Main workflow."""
    print("="*80)
    print("GENERATING PROTO FILES FOR HOME ASSISTANT INTEGRATION")
    print("="*80)
    print()
    
    if not HA_PROTO_DIR.exists():
        print(f"❌ Error: HA proto directory does not exist: {HA_PROTO_DIR}")
        return 1
    
    if not YALENEST_PROTO_DIR.exists():
        print(f"❌ Error: Yalenestlocktest proto directory does not exist: {YALENEST_PROTO_DIR}")
        return 1
    
    # Step 1: Copy proto files
    if not copy_proto_files():
        print("⚠️  No proto files copied. Continuing anyway...")
    
    # Step 2: Compile proto files
    if not compile_proto_files():
        print("❌ Failed to compile proto files")
        return 1
    
    # Step 3: Verify pb2 files
    verify_pb2_files()
    
    print()
    print("="*80)
    print("COMPLETE")
    print("="*80)
    print()
    print("Next steps:")
    print("  1. Update protobuf_handler.py to use the new pb2 files")
    print("  2. Test the integration with the new proto definitions")
    print("  3. Verify all traits decode correctly")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

