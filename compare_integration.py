#!/usr/bin/env python3
"""
Integration Comparison Tool

This tool compares what the ha-nest-yale-integration is currently decoding
vs what's available in the blackboxprotobuf decoded data. It helps identify
gaps and opportunities for improvement.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Set

from fallback_decoder import FallbackDecoder
from protobuf_handler import NestProtobufHandler
import asyncio


def extract_integration_fields(locks_data: Dict[str, Any]) -> Set[str]:
    """Extract field paths from integration's decoded data structure."""
    fields = set()
    
    def traverse(obj: Any, prefix: str = ""):
        if isinstance(obj, dict):
            for key, value in obj.items():
                field_path = f"{prefix}.{key}" if prefix else key
                fields.add(field_path)
                if isinstance(value, (dict, list)):
                    traverse(value, field_path)
        elif isinstance(obj, list):
            for idx, item in enumerate(obj):
                traverse(item, f"{prefix}[{idx}]" if prefix else f"[{idx}]")
    
    traverse(locks_data)
    return fields


def extract_blackbox_fields(blackbox_data: Dict[str, Any]) -> Set[str]:
    """Extract all field paths from blackbox decoded data."""
    fields = set()
    
    def traverse(obj: Any, prefix: str = "", depth: int = 0):
        if depth > 15:  # Prevent infinite recursion
            return
        
        if isinstance(obj, dict):
            for key, value in obj.items():
                field_path = f"{prefix}.{key}" if prefix else str(key)
                fields.add(field_path)
                if isinstance(value, (dict, list)):
                    traverse(value, field_path, depth + 1)
        elif isinstance(obj, list):
            for idx, item in enumerate(obj):
                traverse(item, f"{prefix}[{idx}]" if prefix else f"[{idx}]", depth + 1)
    
    traverse(blackbox_data)
    return fields


async def compare_decoding_methods(raw_data: bytes) -> Dict[str, Any]:
    """Compare integration decoding vs blackbox decoding for the same message."""
    comparison = {
        "integration": {},
        "blackbox": {},
        "integration_fields": set(),
        "blackbox_fields": set(),
        "missing_in_integration": set(),
        "integration_errors": [],
        "blackbox_errors": [],
    }
    
    # Try integration decoding
    handler = NestProtobufHandler()
    try:
        integration_data = await handler._process_message(raw_data)
        comparison["integration"] = integration_data
        comparison["integration_fields"] = extract_integration_fields(integration_data)
    except Exception as e:
        comparison["integration_errors"].append({
            "type": type(e).__name__,
            "message": str(e),
        })
    
    # Try blackbox decoding
    fallback = FallbackDecoder()
    try:
        blackbox_result = fallback.decode(raw_data)
        if blackbox_result:
            comparison["blackbox"] = blackbox_result.get("message", {})
            comparison["blackbox_fields"] = extract_blackbox_fields(comparison["blackbox"])
            
            # Extract structured info from blackbox
            device_info = fallback.extract_device_info(blackbox_result)
            comparison["blackbox_device_info"] = device_info
    except Exception as e:
        comparison["blackbox_errors"].append({
            "type": type(e).__name__,
            "message": str(e),
        })
    
    # Find missing fields
    comparison["missing_in_integration"] = comparison["blackbox_fields"] - comparison["integration_fields"]
    
    return comparison


def analyze_capture_vs_integration(capture_dir: Path) -> Dict[str, Any]:
    """Analyze captured messages using both integration and blackbox methods."""
    results = {
        "directory": str(capture_dir),
        "messages": [],
        "summary": {
            "total_messages": 0,
            "integration_success": 0,
            "blackbox_success": 0,
            "integration_devices": set(),
            "blackbox_devices": set(),
            "integration_structures": set(),
            "blackbox_structures": set(),
            "integration_users": set(),
            "blackbox_users": set(),
            "common_missing_fields": {},
        },
    }
    
    # Find all raw message files
    raw_files = sorted(capture_dir.glob("*.raw.bin"))
    results["summary"]["total_messages"] = len(raw_files)
    
    for raw_file in raw_files:
        print(f"Processing {raw_file.name}...")
        
        with open(raw_file, "rb") as f:
            raw_data = f.read()
        
        comparison = asyncio.run(compare_decoding_methods(raw_data))
        
        message_result = {
            "file": raw_file.name,
            "raw_size": len(raw_data),
            "comparison": comparison,
        }
        
        # Update summary
        integration_data = comparison.get("integration", {})
        if integration_data.get("yale"):
            results["summary"]["integration_success"] += 1
            for device_id in integration_data.get("yale", {}).keys():
                results["summary"]["integration_devices"].add(device_id)
        
        if integration_data.get("structure_id"):
            results["summary"]["integration_structures"].add(integration_data["structure_id"])
        
        if integration_data.get("user_id"):
            results["summary"]["integration_users"].add(integration_data["user_id"])
        
        blackbox_info = comparison.get("blackbox_device_info", {})
        if blackbox_info:
            for device in blackbox_info.get("devices", []):
                results["summary"]["blackbox_devices"].add(device["id"])
            for structure in blackbox_info.get("structures", []):
                results["summary"]["blackbox_structures"].add(structure["id"])
            for user in blackbox_info.get("users", []):
                results["summary"]["blackbox_users"].add(user["id"])
            
            if blackbox_info.get("devices") or blackbox_info.get("structures") or blackbox_info.get("users"):
                results["summary"]["blackbox_success"] += 1
        
        # Track missing fields
        for field in comparison.get("missing_in_integration", set()):
            results["summary"]["common_missing_fields"][field] = (
                results["summary"]["common_missing_fields"].get(field, 0) + 1
            )
        
        results["messages"].append(message_result)
    
    # Convert sets to lists for JSON serialization
    results["summary"]["integration_devices"] = list(results["summary"]["integration_devices"])
    results["summary"]["blackbox_devices"] = list(results["summary"]["blackbox_devices"])
    results["summary"]["integration_structures"] = list(results["summary"]["integration_structures"])
    results["summary"]["blackbox_structures"] = list(results["summary"]["blackbox_structures"])
    results["summary"]["integration_users"] = list(results["summary"]["integration_users"])
    results["summary"]["blackbox_users"] = list(results["summary"]["blackbox_users"])
    
    return results


def generate_comparison_report(analysis: Dict[str, Any], output_file: Path | None = None):
    """Generate a comparison report."""
    lines = []
    lines.append("=" * 80)
    lines.append("INTEGRATION vs BLACKBOX DECODING COMPARISON")
    lines.append("=" * 80)
    lines.append(f"\nDirectory: {analysis['directory']}")
    lines.append(f"Total Messages: {analysis['summary']['total_messages']}")
    lines.append(f"Integration Success: {analysis['summary']['integration_success']}")
    lines.append(f"Blackbox Success: {analysis['summary']['blackbox_success']}")
    
    # Device comparison
    lines.append("\n" + "-" * 80)
    lines.append("DEVICES")
    lines.append("-" * 80)
    integration_devices = set(analysis['summary']['integration_devices'])
    blackbox_devices = set(analysis['summary']['blackbox_devices'])
    
    lines.append(f"Integration found: {len(integration_devices)}")
    for device_id in integration_devices:
        lines.append(f"  - {device_id}")
    
    lines.append(f"\nBlackbox found: {len(blackbox_devices)}")
    for device_id in blackbox_devices:
        lines.append(f"  - {device_id}")
    
    missing_in_integration = blackbox_devices - integration_devices
    if missing_in_integration:
        lines.append(f"\n⚠️  Missing in Integration: {len(missing_in_integration)}")
        for device_id in missing_in_integration:
            lines.append(f"  - {device_id}")
    
    # Structure comparison
    lines.append("\n" + "-" * 80)
    lines.append("STRUCTURES")
    lines.append("-" * 80)
    integration_structures = set(analysis['summary']['integration_structures'])
    blackbox_structures = set(analysis['summary']['blackbox_structures'])
    
    lines.append(f"Integration found: {len(integration_structures)}")
    for structure_id in integration_structures:
        lines.append(f"  - {structure_id}")
    
    lines.append(f"\nBlackbox found: {len(blackbox_structures)}")
    for structure_id in blackbox_structures:
        lines.append(f"  - {structure_id}")
    
    missing_structures = blackbox_structures - integration_structures
    if missing_structures:
        lines.append(f"\n⚠️  Missing in Integration: {len(missing_structures)}")
        for structure_id in missing_structures:
            lines.append(f"  - {structure_id}")
    
    # User comparison
    lines.append("\n" + "-" * 80)
    lines.append("USERS")
    lines.append("-" * 80)
    integration_users = set(analysis['summary']['integration_users'])
    blackbox_users = set(analysis['summary']['blackbox_users'])
    
    lines.append(f"Integration found: {len(integration_users)}")
    for user_id in integration_users:
        lines.append(f"  - {user_id}")
    
    lines.append(f"\nBlackbox found: {len(blackbox_users)}")
    for user_id in blackbox_users:
        lines.append(f"  - {user_id}")
    
    missing_users = blackbox_users - integration_users
    if missing_users:
        lines.append(f"\n⚠️  Missing in Integration: {len(missing_users)}")
        for user_id in missing_users:
            lines.append(f"  - {user_id}")
    
    # Missing fields
    if analysis["summary"]["common_missing_fields"]:
        lines.append("\n" + "-" * 80)
        lines.append("COMMONLY MISSING FIELDS")
        lines.append("-" * 80)
        sorted_fields = sorted(
            analysis["summary"]["common_missing_fields"].items(),
            key=lambda x: x[1],
            reverse=True,
        )
        for field, count in sorted_fields[:30]:  # Top 30
            lines.append(f"  {field} (missing in {count} messages)")
    
    report_text = "\n".join(lines)
    
    if output_file:
        output_file.write_text(report_text)
        print(f"\nReport written to: {output_file}")
    else:
        print(report_text)
    
    return report_text


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Compare integration decoding vs blackbox decoding."
    )
    parser.add_argument(
        "capture_dir",
        type=Path,
        help="Directory containing captured protobuf messages",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output file for the comparison report (default: stdout)",
    )
    parser.add_argument(
        "--json",
        type=Path,
        help="Output detailed comparison as JSON to this file",
    )
    
    args = parser.parse_args(argv)
    
    if not args.capture_dir.exists():
        print(f"Error: Capture directory does not exist: {args.capture_dir}", file=sys.stderr)
        return 1
    
    print(f"Comparing integration vs blackbox decoding for: {args.capture_dir}")
    analysis = analyze_capture_vs_integration(args.capture_dir)
    
    # Generate report
    generate_comparison_report(analysis, args.output)
    
    # Output JSON if requested
    if args.json:
        args.json.write_text(json.dumps(analysis, indent=2, default=str))
        print(f"\nDetailed JSON comparison written to: {args.json}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

