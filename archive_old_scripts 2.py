#!/usr/bin/env python3
"""
Archive old redundant scripts to keep project clean.

Moves old test, capture, and decode scripts to archive/ directory
while preserving git history.
"""

import shutil
from pathlib import Path
import sys

# Scripts to archive
TEST_SCRIPTS = [
    "test_all_device_traits.py",
    "test_all_trait_decoding.py",
    "test_all_traits_final.py",
    "test_decode_all_traits.py",
    "test_traits_from_handler.py",
    "comprehensive_trait_test.py",
    "final_trait_test.py",
    "test_enhanced_handler.py",
    "test_enhanced_handler_live.py",
    "test_enhanced_handler_proper.py",
    "test_boltlock_traits.py",
    "test_model_decoding.py",
    "test_final.py",
    "test_simple_chunk_processing.py",
    "test_message_decoding.py",
    "test_decode_output.py",
    "test_with_existing_proto.py",
    "test_all_proto_files.py",
]

CAPTURE_SCRIPTS = [
    "capture_and_save.py",
    "capture_and_refine_proto.py",
    "capture_fresh_for_proto_refinement.py",
    "capture_homekit_simple.py",
    "capture_homekit_traits.py",
    "capture_with_full_decoding.py",
    "standalone_capture_for_proto.py",
]

DECODE_SCRIPTS = [
    "decode_all_messages.py",
    "decode_hex_message.py",
    "decode_hex_simple.py",
    "decode_homekit_info.py",
    "complete_trait_decoder.py",
    "working_trait_decoder.py",
    "extract_all_homekit_data.py",
    "extract_homekit_info.py",
    "extract_from_hex.py",
    "extract_grpc_messages.py",
    "extract_ids.py",
]

ANALYSIS_SCRIPTS = [
    "analyze_protobuf.py",
    "analyze_stream_format.py",
    "analyze_streambody_structure.py",
    "compare_integration.py",
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
    
    parser = argparse.ArgumentParser(description="Archive old redundant scripts")
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
    parser.add_argument(
        "--category",
        choices=["test", "capture", "decode", "analysis", "all"],
        default="all",
        help="Category to archive (default: all)"
    )
    
    args = parser.parse_args()
    
    print("=" * 80)
    print("ARCHIVING OLD SCRIPTS")
    print("=" * 80)
    print()
    
    if args.dry_run:
        print("DRY RUN MODE - No files will be moved")
        print()
    
    all_archived = []
    all_not_found = []
    
    if args.category in ["test", "all"]:
        print("Archiving test scripts...")
        archived, not_found = archive_scripts(
            TEST_SCRIPTS, args.archive_dir, "test_scripts", args.dry_run
        )
        all_archived.extend(archived)
        all_not_found.extend(not_found)
        print()
    
    if args.category in ["capture", "all"]:
        print("Archiving capture scripts...")
        archived, not_found = archive_scripts(
            CAPTURE_SCRIPTS, args.archive_dir, "capture_scripts", args.dry_run
        )
        all_archived.extend(archived)
        all_not_found.extend(not_found)
        print()
    
    if args.category in ["decode", "all"]:
        print("Archiving decode/extract scripts...")
        archived, not_found = archive_scripts(
            DECODE_SCRIPTS, args.archive_dir, "decode_scripts", args.dry_run
        )
        all_archived.extend(archived)
        all_not_found.extend(not_found)
        print()
    
    if args.category in ["analysis", "all"]:
        print("Archiving analysis scripts...")
        archived, not_found = archive_scripts(
            ANALYSIS_SCRIPTS, args.archive_dir, "analysis_scripts", args.dry_run
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

