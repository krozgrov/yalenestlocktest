#!/usr/bin/env python3
"""
Automated workflow: Capture messages and generate proto files.

This script automates the complete workflow:
1. Capture protobuf messages
2. Extract IDs
3. Generate proto files
4. Compile to pb2.py files
"""

import argparse
import subprocess
import sys
from pathlib import Path
from datetime import datetime


def run_command(cmd, description, check=True):
    """Run a command and handle errors."""
    print(f"\n{'='*80}")
    print(f"{description}")
    print(f"{'='*80}")
    print(f"Running: {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    
    try:
        if isinstance(cmd, str):
            result = subprocess.run(cmd, shell=True, check=check, capture_output=True, text=True)
        else:
            result = subprocess.run(cmd, check=check, capture_output=True, text=True)
        
        if result.stdout:
            print(result.stdout)
        if result.stderr and check:
            print(result.stderr, file=sys.stderr)
        
        return result.returncode == 0 if not check else True
    except subprocess.CalledProcessError as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        if e.stdout:
            print(e.stdout, file=sys.stderr)
        if e.stderr:
            print(e.stderr, file=sys.stderr)
        return False
    except FileNotFoundError as e:
        print(f"❌ Command not found: {e}", file=sys.stderr)
        return False


def find_latest_capture(capture_dir):
    """Find the most recent capture directory."""
    capture_path = Path(capture_dir)
    if not capture_path.exists():
        return None
    
    captures = sorted([d for d in capture_path.iterdir() if d.is_dir()], 
                     key=lambda x: x.stat().st_mtime, reverse=True)
    return captures[0] if captures else None


def main():
    parser = argparse.ArgumentParser(
        description="Automated workflow: Capture messages and generate proto files"
    )
    parser.add_argument(
        "--traits",
        nargs="+",
        default=[
            "nest.trait.user.UserInfoTrait",
            "nest.trait.structure.StructureInfoTrait",
            "weave.trait.security.BoltLockTrait",
            "weave.trait.security.BoltLockSettingsTrait",
            "weave.trait.security.BoltLockCapabilitiesTrait",
            "weave.trait.security.PincodeInputTrait",
            "weave.trait.security.TamperTrait",
        ],
        help="Traits to capture",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=3,
        help="Number of messages to capture",
    )
    parser.add_argument(
        "--output-dir",
        default="captures",
        help="Directory for captures",
    )
    parser.add_argument(
        "--message-name",
        default="StreamBodyMessage",
        help="Name for generated message",
    )
    parser.add_argument(
        "--proto-root",
        default="proto/autogen",
        help="Directory for generated proto files",
    )
    parser.add_argument(
        "--skip-capture",
        action="store_true",
        help="Skip capture step, use existing captures",
    )
    parser.add_argument(
        "--skip-extract",
        action="store_true",
        help="Skip ID extraction step",
    )
    parser.add_argument(
        "--skip-protoc",
        action="store_true",
        help="Skip protoc compilation",
    )
    parser.add_argument(
        "--use-existing",
        type=Path,
        help="Use existing capture directory instead of capturing new",
    )
    
    args = parser.parse_args()
    
    print("="*80)
    print("AUTOMATED PROTO GENERATION WORKFLOW")
    print("="*80)
    
    # Step 1: Capture messages
    if not args.skip_capture and not args.use_existing:
        traits_str = " ".join(f'"{t}"' for t in args.traits)
        cmd = [
            "python", "reverse_engineering.py",
            "--traits"] + args.traits + [
            "--output-dir", args.output_dir,
            "--limit", str(args.limit),
            "--no-parsed",
        ]
        
        if not run_command(cmd, "Step 1: Capturing protobuf messages", check=False):
            print("⚠️  Capture had issues, but continuing...")
    
    # Find capture directory
    if args.use_existing:
        capture_dir = args.use_existing
    else:
        capture_dir = find_latest_capture(args.output_dir)
    
    if not capture_dir or not capture_dir.exists():
        print(f"❌ Error: No capture directory found in {args.output_dir}")
        return 1
    
    print(f"\n✅ Using capture: {capture_dir}")
    
    # Step 2: Extract IDs
    if not args.skip_extract:
        cmd = ["python", "extract_ids.py", str(capture_dir)]
        run_command(cmd, "Step 2: Extracting IDs", check=False)
    
    # Step 3: Generate proto files
    print(f"\n{'='*80}")
    print("Step 3: Generating proto files from typedefs")
    print(f"{'='*80}")
    
    typedef_files = list(capture_dir.glob("*.typedef.json"))
    if not typedef_files:
        print("⚠️  No typedef.json files found.")
        print("   Hint: Run reverse_engineering.py with blackbox enabled to generate typedefs")
        return 1
    
    print(f"   Found {len(typedef_files)} typedef file(s)")
    
    # Try to generate proto
    proto_root = Path(args.proto_root)
    proto_root.mkdir(parents=True, exist_ok=True)
    
    # Use update_proto_from_captures.py
    cmd = [
        "python", "update_proto_from_captures.py",
        str(capture_dir),
        "--message-name", args.message_name,
        "--proto-root", str(proto_root),
    ]
    
    if args.skip_protoc:
        cmd.append("--skip-protoc")
    
    success = run_command(cmd, "   Generating proto files", check=False)
    
    # Step 4: Show results
    print(f"\n{'='*80}")
    print("Step 4: Results")
    print(f"{'='*80}")
    
    message_name_lower = args.message_name.lower()
    proto_file = proto_root / f"{message_name_lower}.proto"
    
    if proto_file.exists():
        print(f"✅ Generated proto file: {proto_file}")
        print(f"   Size: {proto_file.stat().st_size} bytes")
        print(f"\n   First 30 lines:")
        with open(proto_file, "r") as f:
            for i, line in enumerate(f):
                if i >= 30:
                    break
                print(f"   {line.rstrip()}")
    else:
        print(f"⚠️  Proto file not found: {proto_file}")
    
    # Check for pb2 files
    pb2_dir = proto_root / "nest" / "observe"
    if pb2_dir.exists():
        pb2_files = list(pb2_dir.glob("*_pb2.py"))
        if pb2_files:
            print(f"\n✅ Generated pb2 files:")
            for pb2_file in pb2_files:
                print(f"   {pb2_file}")
        else:
            print(f"\nℹ️  No pb2 files found. To generate:")
            print(f"   protoc --proto_path={proto_root} --python_out={proto_root} {proto_file}")
    else:
        print(f"\nℹ️  To generate pb2 files:")
        print(f"   protoc --proto_path={proto_root} --python_out={proto_root} {proto_file}")
    
    print(f"\n{'='*80}")
    print("WORKFLOW COMPLETE")
    print(f"{'='*80}")
    print(f"\nNext steps:")
    print(f"  1. Review: {proto_file}")
    print(f"  2. Improve field names manually if needed")
    print(f"  3. Compile: protoc --proto_path={proto_root} --python_out={proto_root} {proto_file}")
    print(f"  4. Use in code: from proto.autogen.nest.observe import {message_name_lower}_pb2")
    print()
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())

