#!/usr/bin/env python3
"""
Sync proto files with homebridge-nest plugin.

This script:
1. Analyzes current proto files
2. Fetches proto definitions from homebridge-nest (if available)
3. Updates proto files to match homebridge-nest feature parity
4. Generates comprehensive proto coverage
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Set
import urllib.request
import tempfile
import shutil


def get_homebridge_nest_proto_info():
    """Get information about proto files in homebridge-nest."""
    # homebridge-nest is JavaScript, so proto files might be in a different format
    # or embedded in the code. Let's check their repository structure.
    repo_url = "https://api.github.com/repos/krozgrov/homebridge-nest/contents"
    
    print("Fetching homebridge-nest repository structure...")
    try:
        with urllib.request.urlopen(f"{repo_url}") as response:
            contents = json.loads(response.read().decode())
            
        # Look for proto-related files
        proto_info = {
            "proto_files": [],
            "trait_files": [],
            "message_files": [],
        }
        
        for item in contents:
            if item["type"] == "file":
                name = item["name"]
                if ".proto" in name.lower() or "protobuf" in name.lower():
                    proto_info["proto_files"].append(name)
            elif item["type"] == "dir":
                # Check lib directory which likely contains the main code
                if item["name"] == "lib":
                    try:
                        lib_url = f"{repo_url}/lib"
                        with urllib.request.urlopen(lib_url) as lib_response:
                            lib_contents = json.loads(lib_response.read().decode())
                            for lib_item in lib_contents:
                                if "trait" in lib_item["name"].lower() or "message" in lib_item["name"].lower():
                                    proto_info["trait_files"].append(lib_item["name"])
                    except:
                        pass
        
        return proto_info
    except Exception as e:
        print(f"Warning: Could not fetch homebridge-nest info: {e}")
        return None


def analyze_current_proto_files(proto_root: Path) -> Dict[str, List[str]]:
    """Analyze current proto files in the project."""
    proto_files = {}
    
    for proto_file in proto_root.rglob("*.proto"):
        rel_path = proto_file.relative_to(proto_root)
        package = str(rel_path.parent).replace("/", ".").replace("\\", ".")
        
        if package not in proto_files:
            proto_files[package] = []
        
        proto_files[package].append(str(rel_path))
    
    return proto_files


def get_traits_from_captures(capture_dirs: List[Path]) -> Set[str]:
    """Extract all trait types from capture files."""
    traits = set()
    
    for capture_dir in capture_dirs:
        for blackbox_file in capture_dir.glob("*.blackbox.json"):
            try:
                with open(blackbox_file, "r") as f:
                    data = json.load(f)
                
                def extract_traits(obj, path=""):
                    if isinstance(obj, dict):
                        # Look for trait_type patterns
                        for key, value in obj.items():
                            if key == "2" and isinstance(value, str):
                                if "trait" in value.lower():
                                    traits.add(value)
                            extract_traits(value, f"{path}.{key}")
                    elif isinstance(obj, list):
                        for item in obj:
                            extract_traits(item, path)
                
                extract_traits(data)
            except Exception as e:
                print(f"Warning: Could not read {blackbox_file}: {e}")
    
    return traits


def create_comprehensive_proto_update(
    proto_root: Path,
    traits: Set[str],
    output_dir: Path
):
    """Create comprehensive proto file updates based on discovered traits."""
    
    # Known trait categories from homebridge-nest
    trait_categories = {
        "nest.trait.user": ["UserInfoTrait"],
        "nest.trait.structure": ["StructureInfoTrait"],
        "nest.trait.hvac": ["HvacTrait", "HvacSettingsTrait"],
        "nest.trait.occupancy": ["OccupancyTrait"],
        "nest.trait.sensor": ["SensorTrait"],
        "weave.trait.security": [
            "BoltLockTrait",
            "BoltLockSettingsTrait", 
            "BoltLockCapabilitiesTrait",
            "PincodeInputTrait",
            "TamperTrait"
        ],
    }
    
    # Add discovered traits
    for trait in traits:
        parts = trait.split(".")
        if len(parts) >= 3:
            category = ".".join(parts[:-1])
            trait_name = parts[-1]
            if category not in trait_categories:
                trait_categories[category] = []
            if trait_name not in trait_categories[category]:
                trait_categories[category].append(trait_name)
    
    # Generate proto file structure
    updates = {}
    
    for category, trait_list in trait_categories.items():
        proto_path = proto_root / category.replace(".", "/") / "trait.proto"
        proto_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Create or update trait proto file
        proto_content = generate_trait_proto(category, trait_list)
        updates[str(proto_path)] = proto_content
    
    return updates


def generate_trait_proto(package: str, traits: List[str]) -> str:
    """Generate proto file content for traits."""
    lines = [
        'syntax = "proto3";',
        '',
        'import "google/protobuf/any.proto";',
        '',
        f'package {package};',
        '',
    ]
    
    for trait in traits:
        trait_name = trait.replace("Trait", "")
        lines.append(f'// {trait} - Auto-generated placeholder')
        lines.append(f'message {trait_name} {{')
        lines.append('  // Fields will be populated from captures')
        lines.append('  google.protobuf.Any data = 1;')
        lines.append('}')
        lines.append('')
    
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Sync proto files with homebridge-nest feature parity"
    )
    parser.add_argument(
        "--proto-root",
        type=Path,
        default=Path("proto"),
        help="Root directory for proto files",
    )
    parser.add_argument(
        "--captures-dir",
        type=Path,
        default=Path("captures"),
        help="Directory containing capture files",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("proto/updated"),
        help="Directory for updated proto files",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be updated without making changes",
    )
    
    args = parser.parse_args()
    
    print("="*80)
    print("SYNCING PROTO FILES WITH HOMEBRIDGE-NEST")
    print("="*80)
    
    # Step 1: Analyze current proto files
    print("\nStep 1: Analyzing current proto files...")
    current_protos = analyze_current_proto_files(args.proto_root)
    print(f"Found {sum(len(files) for files in current_protos.values())} proto files")
    for package, files in current_protos.items():
        print(f"  {package}: {len(files)} files")
    
    # Step 2: Get homebridge-nest info
    print("\nStep 2: Fetching homebridge-nest information...")
    hb_info = get_homebridge_nest_proto_info()
    if hb_info:
        print(f"Found {len(hb_info.get('proto_files', []))} proto-related files")
    
    # Step 3: Extract traits from captures
    print("\nStep 3: Extracting traits from captures...")
    capture_dirs = [d for d in args.captures_dir.iterdir() if d.is_dir()] if args.captures_dir.exists() else []
    traits = get_traits_from_captures(capture_dirs)
    print(f"Found {len(traits)} unique traits")
    for trait in sorted(traits)[:20]:  # Show first 20
        print(f"  - {trait}")
    
    # Step 4: Generate comprehensive proto updates
    print("\nStep 4: Generating proto file updates...")
    updates = create_comprehensive_proto_update(
        args.output_dir,
        traits,
        args.output_dir
    )
    
    print(f"Generated {len(updates)} proto file updates")
    
    # Step 5: Write updates
    if not args.dry_run:
        print("\nStep 5: Writing updated proto files...")
        for proto_path, content in updates.items():
            path = Path(proto_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            print(f"  ✅ {path}")
    else:
        print("\nStep 5: (Dry run - not writing files)")
        for proto_path, content in updates.items():
            print(f"  Would create: {proto_path}")
            print(f"    Size: {len(content)} bytes")
    
    print("\n" + "="*80)
    print("SYNC COMPLETE")
    print("="*80)
    print("\nNext steps:")
    print("  1. Review generated proto files")
    print("  2. Update with actual field definitions from captures")
    print("  3. Compile with protoc")
    print("  4. Test with your integration")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

