#!/usr/bin/env python3
"""
Unified Testing Tool for Protobuf Decoding

Consolidates all test functionality into a single tool.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Dict, Any, Optional

from proto_decode import ProtoDecoder, load_data_from_file
from protobuf_handler_enhanced import EnhancedProtobufHandler
from auth import GetSessionWithAuth
from const import ENDPOINT_OBSERVE, URL_PROTOBUF, PRODUCTION_HOSTNAME, API_TIMEOUT_SECONDS, USER_AGENT_STRING
import requests
from proto.nestlabs.gateway import v2_pb2


def test_capture_file(capture_file: Path, use_enhanced: bool = True) -> Dict[str, Any]:
    """Test decoding a captured file."""
    print(f"Testing capture file: {capture_file}")
    
    if not capture_file.exists():
        return {"error": f"File not found: {capture_file}"}
    
    # Load raw data
    try:
        raw_data = capture_file.read_bytes()
    except Exception as e:
        return {"error": f"Failed to read file: {e}"}
    
    # Try different decoders
    results = {
        "file": str(capture_file),
        "size_bytes": len(raw_data),
        "decoders": {}
    }
    
    # General-purpose decoder
    decoder = ProtoDecoder(proto_path=Path("proto"))
    general_result = decoder.decode(raw_data, message_type="nest.rpc.StreamBody", use_blackbox=True)
    results["decoders"]["general"] = general_result
    
    # Enhanced handler (Nest-specific)
    if use_enhanced:
        try:
            handler = EnhancedProtobufHandler()
            async def process():
                return await handler._process_message(raw_data)
            nest_result = asyncio.run(process())
            results["decoders"]["enhanced_handler"] = nest_result
        except Exception as e:
            results["decoders"]["enhanced_handler"] = {"error": str(e)}
    
    return results


def test_capture_directory(capture_dir: Path, pattern: str = "*.raw.bin") -> Dict[str, Any]:
    """Test all capture files in a directory."""
    if not capture_dir.exists():
        return {"error": f"Directory not found: {capture_dir}"}
    
    capture_files = sorted(capture_dir.glob(pattern))
    if not capture_files:
        return {"error": f"No {pattern} files found in {capture_dir}"}
    
    results = {
        "directory": str(capture_dir),
        "files_tested": len(capture_files),
        "results": []
    }
    
    for capture_file in capture_files:
        file_result = test_capture_file(capture_file)
        results["results"].append(file_result)
    
    return results


def test_live_stream(traits: Optional[list[str]] = None, limit: int = 5) -> Dict[str, Any]:
    """Test decoding from live stream."""
    print("Testing live stream...")
    
    try:
        session, access_token, user_id, transport_url = GetSessionWithAuth()
    except Exception as e:
        return {"error": f"Authentication failed: {e}"}
    
    # Build observe request
    req = v2_pb2.ObserveRequest(version=2, subscribe=True)
    if traits:
        trait_names = traits
    else:
        trait_names = [
            "nest.trait.user.UserInfoTrait",
            "nest.trait.structure.StructureInfoTrait",
            "weave.trait.security.BoltLockTrait",
            "weave.trait.description.DeviceIdentityTrait",
            "weave.trait.power.BatteryPowerSourceTrait",
        ]
    
    for trait_name in trait_names:
        filt = req.filter.add()
        filt.trait_type = trait_name
    
    payload = req.SerializeToString()
    
    headers = {
        'Accept-Encoding': 'gzip, deflate, br, zstd',
        'Content-Type': 'application/x-protobuf',
        'User-Agent': USER_AGENT_STRING,
        'X-Accept-Response-Streaming': 'true',
        'Accept': 'application/x-protobuf',
        'referer': 'https://home.nest.com/',
        'origin': 'https://home.nest.com',
        'X-Accept-Content-Transfer-Encoding': 'binary',
        'Authorization': 'Basic ' + access_token
    }
    
    # Try to connect
    base_url = URL_PROTOBUF.format(grpc_hostname=PRODUCTION_HOSTNAME["grpc_hostname"])
    target_url = f"{base_url}{ENDPOINT_OBSERVE}"
    
    try:
        response = session.post(target_url, headers=headers, data=payload, stream=True, timeout=(API_TIMEOUT_SECONDS, API_TIMEOUT_SECONDS))
        response.raise_for_status()
    except Exception as e:
        session.close()
        return {"error": f"Stream connection failed: {e}"}
    
    # Process stream
    handler = EnhancedProtobufHandler()
    results = {
        "stream_url": target_url,
        "messages_processed": 0,
        "data": {}
    }
    
    try:
        message_count = 0
        for chunk in response.iter_content(chunk_size=None):
            if chunk:
                data = asyncio.run(handler._process_message(chunk))
                if data:
                    results["data"].update(data)
                message_count += 1
                if message_count >= limit:
                    break
        results["messages_processed"] = message_count
    finally:
        response.close()
        session.close()
    
    return results


def test_all_traits(capture_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Test decoding all known traits."""
    if capture_dir:
        return test_capture_directory(capture_dir)
    else:
        # Use latest capture
        captures_dir = Path("captures")
        if not captures_dir.exists():
            return {"error": "No captures directory found"}
        
        capture_dirs = sorted([d for d in captures_dir.iterdir() if d.is_dir()],
                             key=lambda x: x.stat().st_mtime, reverse=True)
        if not capture_dirs:
            return {"error": "No capture directories found"}
        
        return test_capture_directory(capture_dirs[0])


def main():
    parser = argparse.ArgumentParser(
        description="Unified Testing Tool for Protobuf Decoding",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test a specific capture file
  python test_tool.py file captures/latest/00001.raw.bin
  
  # Test all files in a capture directory
  python test_tool.py directory captures/latest
  
  # Test live stream
  python test_tool.py stream --limit 3
  
  # Test all traits from latest capture
  python test_tool.py all-traits
  
  # Test with specific traits
  python test_tool.py stream --traits DeviceIdentityTrait BatteryPowerSourceTrait
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Test command")
    
    # File test
    file_parser = subparsers.add_parser("file", help="Test a specific capture file")
    file_parser.add_argument("file", type=Path, help="Capture file to test")
    file_parser.add_argument("--no-enhanced", action="store_true", help="Don't use enhanced handler")
    
    # Directory test
    dir_parser = subparsers.add_parser("directory", help="Test all files in a capture directory")
    dir_parser.add_argument("directory", type=Path, help="Capture directory to test")
    dir_parser.add_argument("--pattern", default="*.raw.bin", help="File pattern (default: *.raw.bin)")
    
    # Stream test
    stream_parser = subparsers.add_parser("stream", help="Test live stream")
    stream_parser.add_argument("--traits", nargs="+", help="Specific traits to request")
    stream_parser.add_argument("--limit", type=int, default=5, help="Max messages to process")
    
    # All traits test
    all_parser = subparsers.add_parser("all-traits", help="Test all traits from latest capture")
    all_parser.add_argument("--capture-dir", type=Path, help="Specific capture directory (default: latest)")
    
    # Output options
    parser.add_argument("--output", choices=["json", "pretty"], default="pretty", help="Output format")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    try:
        if args.command == "file":
            result = test_capture_file(args.file, use_enhanced=not args.no_enhanced)
        elif args.command == "directory":
            result = test_capture_directory(args.directory, pattern=args.pattern)
        elif args.command == "stream":
            result = test_live_stream(traits=args.traits, limit=args.limit)
        elif args.command == "all-traits":
            result = test_all_traits(capture_dir=args.capture_dir)
        else:
            parser.print_help()
            return 1
        
        if args.output == "json":
            print(json.dumps(result, indent=2))
        else:
            _print_test_results(result)
        
        return 0
    except KeyboardInterrupt:
        print("\nInterrupted by user.", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


def _print_test_results(result: Dict[str, Any]):
    """Print test results in a pretty format."""
    if "error" in result:
        print(f"❌ Error: {result['error']}")
        return
    
    print("=" * 80)
    print("TEST RESULTS")
    print("=" * 80)
    print()
    
    if "file" in result:
        print(f"File: {result['file']}")
        print(f"Size: {result['size_bytes']} bytes")
        print()
        
        for decoder_name, decoder_result in result.get("decoders", {}).items():
            print(f"Decoder: {decoder_name}")
            if "error" in decoder_result:
                print(f"  ❌ Error: {decoder_result['error']}")
            else:
                print(f"  ✅ Success")
                if "message_count" in decoder_result:
                    print(f"  Messages: {decoder_result['message_count']}")
            print()
    
    elif "directory" in result:
        print(f"Directory: {result['directory']}")
        print(f"Files tested: {result['files_tested']}")
        print()
        
        for file_result in result.get("results", []):
            if "error" in file_result:
                print(f"❌ {file_result.get('file', 'unknown')}: {file_result['error']}")
            else:
                print(f"✅ {file_result.get('file', 'unknown')}: {file_result.get('size_bytes', 0)} bytes")
        print()
    
    elif "stream_url" in result:
        print(f"Stream: {result['stream_url']}")
        print(f"Messages processed: {result['messages_processed']}")
        print()
        
        data = result.get("data", {})
        if data:
            print("Decoded data:")
            print(json.dumps(data, indent=2))
        print()


if __name__ == "__main__":
    sys.exit(main())

