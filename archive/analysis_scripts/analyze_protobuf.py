#!/usr/bin/env python3
"""
Protobuf Analysis Tool

This tool analyzes captured protobuf messages to:
1. Compare blackboxprotobuf decoding vs structured proto decoding
2. Identify fields that are available but not being decoded
3. Suggest improvements to proto definitions
4. Generate reports on decoding coverage
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, Set

try:
    import blackboxprotobuf as bbp  # noqa: F401
    BLACKBOX_AVAILABLE = True
except ImportError:
    BLACKBOX_AVAILABLE = False
    print("Warning: blackboxprotobuf not available. Some features will be limited.", file=sys.stderr)

try:
    from google.protobuf.message import DecodeError
    PROTOBUF_AVAILABLE = True
except ImportError:
    PROTOBUF_AVAILABLE = False
    DecodeError = Exception  # type: ignore
    print("Warning: google.protobuf not available. Install with: pip install protobuf", file=sys.stderr)

try:
    from proto.nest import rpc_pb2 as rpc
    PROTO_AVAILABLE = True
except ImportError:
    PROTO_AVAILABLE = False
    rpc = None  # type: ignore
    print("Warning: Proto modules not available. Some features will be limited.", file=sys.stderr)


def extract_nested_fields(data: Any, prefix: str = "", max_depth: int = 10) -> Set[str]:
    """Extract all field paths from a nested dictionary/object."""
    fields = set()
    
    if max_depth <= 0:
        return fields
    
    if isinstance(data, dict):
        for key, value in data.items():
            field_path = f"{prefix}.{key}" if prefix else key
            fields.add(field_path)
            if isinstance(value, (dict, list)):
                fields.update(extract_nested_fields(value, field_path, max_depth - 1))
    elif isinstance(data, list):
        for idx, item in enumerate(data):
            field_path = f"{prefix}[{idx}]" if prefix else f"[{idx}]"
            if isinstance(item, (dict, list)):
                fields.update(extract_nested_fields(item, field_path, max_depth - 1))
    
    return fields


def extract_device_info(blackbox_data: Dict[str, Any]) -> Dict[str, Any]:
    """Extract device, structure, and user information from blackbox decoded data."""
    info = {
        "devices": [],
        "structures": [],
        "users": [],
        "traits": {},
    }
    
    def traverse(obj: Any, path: str = ""):
        if isinstance(obj, dict):
            # Look for device IDs
            if "1" in obj and isinstance(obj["1"], str):
                device_id = obj["1"]
                resource_type = obj.get("2", "")
                if not isinstance(resource_type, str):
                    resource_type = str(resource_type) if resource_type else ""
                
                if "yale.resource" in resource_type or "LinusLockResource" in resource_type:
                    traits = []
                    if "4" in obj:
                        trait_list = obj["4"] if isinstance(obj["4"], list) else [obj["4"]]
                        for trait in trait_list:
                            if isinstance(trait, dict) and "2" in trait:
                                traits.append(trait["2"])
                    
                    info["devices"].append({
                        "id": device_id,
                        "type": resource_type,
                        "traits": traits,
                        "path": path,
                    })
                
                elif "structure" in resource_type.lower():
                    info["structures"].append({
                        "id": device_id,
                        "type": resource_type,
                        "path": path,
                    })
                
                elif "user" in resource_type.lower():
                    info["users"].append({
                        "id": device_id,
                        "type": resource_type,
                        "path": path,
                    })
            
            for key, value in obj.items():
                traverse(value, f"{path}.{key}" if path else key)
        
        elif isinstance(obj, list):
            for idx, item in enumerate(obj):
                traverse(item, f"{path}[{idx}]")
    
    traverse(blackbox_data)
    return info


def compare_decodings(
    raw_data: bytes,
    blackbox_json: Dict[str, Any],
    parsed_json: Dict[str, Any],
) -> Dict[str, Any]:
    """Compare blackbox and structured decoding results."""
    comparison = {
        "blackbox_fields": set(),
        "parsed_fields": set(),
        "missing_in_parsed": set(),
        "missing_in_blackbox": set(),
        "device_info": {},
        "decoding_errors": [],
    }
    
    # Extract fields from blackbox decoding
    comparison["blackbox_fields"] = extract_nested_fields(blackbox_json)
    
    # Extract fields from structured decoding
    comparison["parsed_fields"] = extract_nested_fields(parsed_json)
    
    # Find fields available in blackbox but not in parsed
    comparison["missing_in_parsed"] = comparison["blackbox_fields"] - comparison["parsed_fields"]
    
    # Find fields available in parsed but not in blackbox
    comparison["missing_in_blackbox"] = comparison["parsed_fields"] - comparison["blackbox_fields"]
    
    # Extract device information from blackbox
    comparison["device_info"] = extract_device_info(blackbox_json)
    
    # Try structured decoding and capture errors
    if not PROTO_AVAILABLE or not PROTOBUF_AVAILABLE:
        return comparison
    
    try:
        if rpc and hasattr(rpc, "StreamBody"):
            stream_body = rpc.StreamBody()  # type: ignore
            stream_body.ParseFromString(raw_data)
    except (DecodeError, Exception) as e:  # type: ignore
        comparison["decoding_errors"].append({
            "type": "DecodeError",
            "message": str(e),
        })
    except (AttributeError, TypeError) as e:
        comparison["decoding_errors"].append({
            "type": type(e).__name__,
            "message": str(e),
        })
    
    return comparison


def analyze_capture_directory(capture_dir: Path) -> Dict[str, Any]:
    """Analyze all captured messages in a directory."""
    results = {
        "directory": str(capture_dir),
        "messages": [],
        "summary": {
            "total_messages": 0,
            "successful_blackbox": 0,
            "successful_parsed": 0,
            "all_devices": set(),
            "all_structures": set(),
            "all_users": set(),
            "common_missing_fields": {},
        },
    }
    
    # Find all message files
    raw_files = sorted(capture_dir.glob("*.raw.bin"))
    results["summary"]["total_messages"] = len(raw_files)
    
    for raw_file in raw_files:
        prefix = raw_file.stem.replace(".raw", "")
        blackbox_file = capture_dir / f"{prefix}.blackbox.json"
        parsed_file = capture_dir / f"{prefix}.parsed.json"
        
        message_result = {
            "file": raw_file.name,
            "raw_size": raw_file.stat().st_size,
            "blackbox_available": blackbox_file.exists(),
            "parsed_available": parsed_file.exists(),
            "comparison": None,
        }
        
        if blackbox_file.exists():
            try:
                with open(blackbox_file, "r", encoding="utf-8") as f:
                    blackbox_data = json.load(f)
                results["summary"]["successful_blackbox"] += 1
                
                parsed_data = {}
                if parsed_file.exists():
                    try:
                        with open(parsed_file, "r", encoding="utf-8") as f:
                            parsed_data = json.load(f)
                        if parsed_data:
                            results["summary"]["successful_parsed"] += 1
                    except (json.JSONDecodeError, OSError) as e:
                        message_result["parsed_error"] = str(e)
                
                # Compare decodings
                if PROTO_AVAILABLE:
                    with open(raw_file, "rb") as f:
                        raw_data = f.read()
                    
                    comparison = compare_decodings(raw_data, blackbox_data, parsed_data)
                else:
                    comparison = {
                        "blackbox_fields": extract_nested_fields(blackbox_data),
                        "parsed_fields": extract_nested_fields(parsed_data),
                        "missing_in_parsed": set(),
                        "missing_in_blackbox": set(),
                        "device_info": extract_device_info(blackbox_data),
                        "decoding_errors": [],
                    }
                
                message_result["comparison"] = comparison
                
                # Aggregate device info
                if comparison.get("device_info"):
                    for device in comparison["device_info"].get("devices", []):
                        results["summary"]["all_devices"].add(device["id"])
                    for structure in comparison["device_info"].get("structures", []):
                        results["summary"]["all_structures"].add(structure["id"])
                    for user in comparison["device_info"].get("users", []):
                        results["summary"]["all_users"].add(user["id"])
                
                # Track missing fields
                for field in comparison.get("missing_in_parsed", []):
                    results["summary"]["common_missing_fields"][field] = (
                        results["summary"]["common_missing_fields"].get(field, 0) + 1
                    )
                
            except (json.JSONDecodeError, OSError, KeyError) as e:
                message_result["error"] = str(e)
        
        results["messages"].append(message_result)
    
    # Convert sets to lists for JSON serialization
    results["summary"]["all_devices"] = list(results["summary"]["all_devices"])
    results["summary"]["all_structures"] = list(results["summary"]["all_structures"])
    results["summary"]["all_users"] = list(results["summary"]["all_users"])
    
    return results


def generate_report(analysis: Dict[str, Any], output_file: Path | None = None):
    """Generate a human-readable report from analysis results."""
    lines = []
    lines.append("=" * 80)
    lines.append("PROTOBUF DECODING ANALYSIS REPORT")
    lines.append("=" * 80)
    lines.append(f"\nDirectory: {analysis['directory']}")
    lines.append(f"Total Messages: {analysis['summary']['total_messages']}")
    lines.append(f"Successful Blackbox Decodes: {analysis['summary']['successful_blackbox']}")
    lines.append(f"Successful Parsed Decodes: {analysis['summary']['successful_parsed']}")
    
    if analysis["summary"]["all_devices"]:
        lines.append(f"\nDevices Found: {len(analysis['summary']['all_devices'])}")
        for device_id in analysis["summary"]["all_devices"]:
            lines.append(f"  - {device_id}")
    
    if analysis["summary"]["all_structures"]:
        lines.append(f"\nStructures Found: {len(analysis['summary']['all_structures'])}")
        for structure_id in analysis["summary"]["all_structures"]:
            lines.append(f"  - {structure_id}")
    
    if analysis["summary"]["all_users"]:
        lines.append(f"\nUsers Found: {len(analysis['summary']['all_users'])}")
        for user_id in analysis["summary"]["all_users"]:
            lines.append(f"  - {user_id}")
    
    if analysis["summary"]["common_missing_fields"]:
        lines.append("\n" + "=" * 80)
        lines.append("COMMONLY MISSING FIELDS (in parsed but available in blackbox)")
        lines.append("=" * 80)
        sorted_fields = sorted(
            analysis["summary"]["common_missing_fields"].items(),
            key=lambda x: x[1],
            reverse=True,
        )
        for field, count in sorted_fields[:20]:  # Top 20
            lines.append(f"  {field} (missing in {count} messages)")
    
    lines.append("\n" + "=" * 80)
    lines.append("MESSAGE-BY-MESSAGE ANALYSIS")
    lines.append("=" * 80)
    
    for msg in analysis["messages"]:
        lines.append(f"\n{msg['file']}:")
        lines.append(f"  Size: {msg['raw_size']} bytes")
        lines.append(f"  Blackbox: {'✓' if msg['blackbox_available'] else '✗'}")
        lines.append(f"  Parsed: {'✓' if msg['parsed_available'] else '✗'}")
        
        if msg.get("comparison"):
            comp = msg["comparison"]
            lines.append(f"  Blackbox Fields: {len(comp['blackbox_fields'])}")
            lines.append(f"  Parsed Fields: {len(comp['parsed_fields'])}")
            lines.append(f"  Missing in Parsed: {len(comp['missing_in_parsed'])}")
            
            if comp.get("device_info"):
                devices = comp["device_info"].get("devices", [])
                if devices:
                    lines.append(f"  Devices: {len(devices)}")
                    for device in devices:
                        lines.append(f"    - {device['id']} ({device['type']})")
                        if device.get("traits"):
                            lines.append(f"      Traits: {', '.join(device['traits'])}")
    
    report_text = "\n".join(lines)
    
    if output_file:
        output_file.write_text(report_text)
        print(f"\nReport written to: {output_file}")
    else:
        print(report_text)
    
    return report_text


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Analyze protobuf decoding coverage and identify missing fields."
    )
    parser.add_argument(
        "capture_dir",
        type=Path,
        help="Directory containing captured protobuf messages",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output file for the analysis report (default: stdout)",
    )
    parser.add_argument(
        "--json",
        type=Path,
        help="Output detailed analysis as JSON to this file",
    )
    
    args = parser.parse_args(argv)
    
    if not args.capture_dir.exists():
        print(f"Error: Capture directory does not exist: {args.capture_dir}", file=sys.stderr)
        return 1
    
    print(f"Analyzing capture directory: {args.capture_dir}")
    analysis = analyze_capture_directory(args.capture_dir)
    
    # Generate report
    generate_report(analysis, args.output)
    
    # Output JSON if requested
    if args.json:
        args.json.write_text(json.dumps(analysis, indent=2, default=str))
        print(f"\nDetailed JSON analysis written to: {args.json}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

