#!/usr/bin/env python3
"""
Analyze StreamBody structure by testing which messages parse successfully.

This script:
1. Uses test_enhanced_handler to capture messages
2. Tests each message against StreamBody proto
3. Identifies which messages parse and which fail
4. Analyzes the structure of successful vs failed messages
"""

import sys
import asyncio
import json
from pathlib import Path
from typing import Dict, Any, List

from protobuf_handler import NestProtobufHandler
from proto.nest import rpc_pb2

try:
    import blackboxprotobuf as bbp
    BLACKBOX_AVAILABLE = True
except ImportError:
    BLACKBOX_AVAILABLE = False


def test_message_parsing(message: bytes) -> Dict[str, Any]:
    """Test if a message parses as StreamBody."""
    result = {
        "length": len(message),
        "parses": False,
        "error": None,
        "structure": None,
    }
    
    try:
        stream_body = rpc_pb2.StreamBody()
        stream_body.ParseFromString(message)
        result["parses"] = True
        result["structure"] = {
            "message_count": len(stream_body.message),
            "has_status": stream_body.HasField("status"),
            "noop_count": len(stream_body.noop),
        }
    except Exception as e:
        result["error"] = str(e)
    
    return result


def analyze_with_blackbox(message: bytes) -> Dict[str, Any]:
    """Analyze message structure with blackboxprotobuf."""
    if not BLACKBOX_AVAILABLE:
        return {"error": "blackboxprotobuf not available"}
    
    try:
        message_json, typedef = bbp.protobuf_to_json(message)
        return {
            "success": True,
            "typedef": typedef,
            "json_preview": json.dumps(message_json, indent=2)[:500],
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


async def analyze_capture_file(capture_file: Path):
    """Analyze a capture file to understand message structure."""
    print(f"\n{'='*80}")
    print(f"Analyzing: {capture_file.name}")
    print(f"{'='*80}\n")
    
    handler = NestProtobufHandler()
    
    with open(capture_file, "rb") as f:
        raw_data = f.read()
    
    print(f"Raw data: {len(raw_data)} bytes\n")
    
    # Extract all messages
    messages = []
    pos = 0
    while pos < len(raw_data):
        length, offset = handler._decode_varint(raw_data, pos)
        if length is None or length == 0:
            break
        if offset + length <= len(raw_data):
            messages.append(raw_data[offset:offset + length])
            pos = offset + length
        else:
            break
    
    print(f"Extracted {len(messages)} message(s)\n")
    
    # Test each message
    parsing_results = []
    successful = []
    failed = []
    
    for i, message in enumerate(messages, 1):
        print(f"Message {i}: {len(message)} bytes", end=" - ")
        
        result = test_message_parsing(message)
        parsing_results.append(result)
        
        if result["parses"]:
            successful.append((i, message, result))
            print("✅ Parses successfully")
            if result["structure"]:
                print(f"   Messages: {result['structure']['message_count']}")
        else:
            failed.append((i, message, result))
            print(f"❌ Fails: {result['error']}")
            
            # Try blackboxprotobuf on failed messages
            if BLACKBOX_AVAILABLE and len(message) > 50:  # Skip tiny messages
                blackbox_result = analyze_with_blackbox(message)
                if blackbox_result.get("success"):
                    print(f"   Blackbox fields: {list(blackbox_result['typedef'].keys())}")
    
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}\n")
    print(f"Total messages: {len(messages)}")
    print(f"✅ Parse successfully: {len(successful)}")
    print(f"❌ Fail to parse: {len(failed)}")
    print()
    
    # Analyze successful messages
    if successful:
        print("Successful messages:")
        for i, msg, result in successful:
            print(f"  Message {i}: {len(msg)} bytes")
            if result["structure"]:
                print(f"    - {result['structure']['message_count']} NestMessage(s)")
        print()
    
    # Analyze failed messages
    if failed:
        print("Failed messages:")
        for i, msg, result in failed:
            print(f"  Message {i}: {len(msg)} bytes - {result['error']}")
        print()
        
        # Try to understand why they fail
        print("Analyzing failed message structures...")
        for i, msg, result in failed[:3]:  # Analyze first 3 failed
            if len(msg) > 50:
                print(f"\n  Message {i} structure:")
                blackbox_result = analyze_with_blackbox(msg)
                if blackbox_result.get("success"):
                    typedef = blackbox_result["typedef"]
                    print(f"    Fields: {list(typedef.keys())}")
                    # Show first level structure
                    for field_num, field_info in list(typedef.items())[:5]:
                        field_type = field_info.get("type", "unknown")
                        print(f"      Field {field_num}: {field_type}")
    
    return {
        "total": len(messages),
        "successful": len(successful),
        "failed": len(failed),
        "parsing_results": parsing_results,
    }


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Analyze StreamBody message structure"
    )
    parser.add_argument(
        "--capture-dir",
        type=Path,
        help="Capture directory to analyze",
    )
    parser.add_argument(
        "--file",
        type=Path,
        help="Specific file to analyze",
    )
    
    args = parser.parse_args()
    
    if args.file:
        files = [args.file]
    elif args.capture_dir:
        files = sorted(args.capture_dir.glob("*.raw.bin"))
    else:
        # Use latest capture
        captures_dir = Path("captures")
        capture_dirs = sorted([d for d in captures_dir.iterdir() if d.is_dir()],
                            key=lambda x: x.stat().st_mtime, reverse=True)
        if not capture_dirs:
            print("Error: No captures found")
            return 1
        files = sorted(capture_dirs[0].glob("*.raw.bin"))
    
    if not files:
        print("Error: No raw.bin files found")
        return 1
    
    print("="*80)
    print("STREAMBODY STRUCTURE ANALYSIS")
    print("="*80)
    
    all_results = []
    for capture_file in files:
        result = asyncio.run(analyze_capture_file(capture_file))
        all_results.append(result)
    
    # Overall summary
    print(f"\n{'='*80}")
    print("OVERALL SUMMARY")
    print(f"{'='*80}\n")
    
    total_messages = sum(r["total"] for r in all_results)
    total_successful = sum(r["successful"] for r in all_results)
    total_failed = sum(r["failed"] for r in all_results)
    
    print(f"Total messages analyzed: {total_messages}")
    print(f"✅ Parse successfully: {total_successful} ({100*total_successful/total_messages:.1f}%)")
    print(f"❌ Fail to parse: {total_failed} ({100*total_failed/total_messages:.1f}%)")
    print()
    
    if total_failed > 0:
        print("⚠️  Some messages fail to parse - proto definitions may be incomplete")
        print("   Review failed message structures above to identify missing fields")
    else:
        print("✅ All messages parse successfully!")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

