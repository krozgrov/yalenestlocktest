#!/usr/bin/env python3
"""
Archive development and proto tool scripts.

These are useful for development but not needed for end users.
"""

import shutil
from pathlib import Path
import sys

# Development/Proto tools to archive
DEV_TOOLS = [
    "automate_workflow.py",
    "compare_typedef_with_proto.py",
    "enhanced_protobuf_handler.py",  # Duplicate of protobuf_handler_enhanced.py
    "fallback_decoder.py",
    "find_serial_number.py",
    "fix_proto_imports.py",
    "generate_ha_proto_files.py",
    "homekit_protobuf_patch.py",
    "map_typedef_to_proto.py",
    "protobuf_manager.py",
    "refine_proto_from_blackbox.py",
    "refine_proto_workflow.py",
    "show_decoded_output.py",
    "sync_with_homebridge_nest.py",
    "update_all_proto_files.py",
    "update_proto_from_captures.py",
    "INTEGRATION_EXAMPLE.py",
]

# Test scripts (duplicates or one-off tests)
TEST_SCRIPTS = [
    "test_nest_url.py",  # Duplicate of test_nest_url_live.py
]


def archive_scripts(scripts: list[str], archive_dir: Path, category: str, dry_run: bool = False):
    """Archive scripts to a category directory."""
    category_dir = archive_dir / category
    if not dry_run:
        category_dir.mkdir(parents=True, exist_ok=True)
    
    archived = []
    not_found = []
    
    for script in scripts:
        script_path = Path(script)
        if script_path.exists():
            dest = category_dir / script_path.name
            if not dry_run:
                shutil.move(str(script_path), str(dest))
            archived.append(script)
            print(f"{'[DRY RUN] ' if dry_run else ''}Moved: {script} -> {dest}")
        else:
            not_found.append(script)
            print(f"Not found (skipping): {script}")
    
    return archived, not_found


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Archive development and proto tool scripts")
    parser.add_argument(
        "--archive-dir",
        type=Path,
        default=Path("archive"),
        help="Archive directory (default: archive/)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be archived without actually moving files"
    )
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("ARCHIVING DEVELOPMENT TOOLS")
    print("=" * 80)
    print()
    
    if args.dry_run:
        print("DRY RUN MODE - No files will be moved")
        print()
    
    all_archived = []
    all_not_found = []
    
    print("Archiving development/proto tools...")
    archived, not_found = archive_scripts(
        DEV_TOOLS, args.archive_dir, "dev_tools", args.dry_run
    )
    all_archived.extend(archived)
    all_not_found.extend(not_found)
    print()
    
    print("Archiving duplicate test scripts...")
    archived, not_found = archive_scripts(
        TEST_SCRIPTS, args.archive_dir, "test_scripts", args.dry_run
    )
    all_archived.extend(archived)
    all_not_found.extend(not_found)
    print()
    
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Archived: {len(all_archived)} files")
    print(f"Not found: {len(all_not_found)} files")
    print()
    
    if all_not_found:
        print("Files not found (may have been already archived or don't exist):")
        for script in all_not_found:
            print(f"  - {script}")
    
    if not args.dry_run and all_archived:
        print()
        print(f"✅ Scripts archived to: {args.archive_dir}")
        print("   (Files are preserved in git history)")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

