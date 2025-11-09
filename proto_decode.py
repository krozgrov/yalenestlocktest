#!/usr/bin/env python3
"""
General-purpose Protobuf Decoder CLI

Decode protobuf messages from any service, with support for:
- Raw binary files
- Hex strings
- Base64 encoded data
- gRPC-web streams
- Custom proto definitions

This tool is service-agnostic and can work with any protobuf messages.
"""

import argparse
import base64
import json
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List
import importlib
import importlib.util

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

try:
    from google.protobuf import message_factory, descriptor_pool, descriptor_database
    from google.protobuf.descriptor_pb2 import FileDescriptorProto
    from google.protobuf import json_format
    PROTOBUF_AVAILABLE = True
except ImportError:
    PROTOBUF_AVAILABLE = False
    print("Warning: protobuf not available. Install with: pip install protobuf", file=sys.stderr)

try:
    import blackboxprotobuf as bbp
    BLACKBOX_AVAILABLE = True
except ImportError:
    BLACKBOX_AVAILABLE = False


class ProtoDecoder:
    """General-purpose protobuf decoder."""
    
    def __init__(self, proto_path: Optional[Path] = None, proto_module: Optional[str] = None):
        """Initialize decoder with optional proto files or module.
        
        Args:
            proto_path: Path to directory containing .proto files or pb2.py files
            proto_module: Python module name containing proto definitions
        """
        self.proto_path = proto_path
        self.proto_module = proto_module
        self.descriptor_pool = None
        self.message_factory = None
        
        if PROTOBUF_AVAILABLE:
            self._setup_descriptor_pool()
    
    def _setup_descriptor_pool(self):
        """Set up descriptor pool for proto files."""
        self.descriptor_pool = descriptor_pool.DescriptorPool()
        self.descriptor_db = descriptor_database.DescriptorDatabase()
        
        # Load proto files if path provided
        if self.proto_path and self.proto_path.exists():
            self._load_proto_files(self.proto_path)
        
        # Load proto module if provided
        if self.proto_module:
            self._load_proto_module(self.proto_module)
    
    def _load_proto_files(self, path: Path):
        """Load all pb2.py files from a directory."""
        import importlib
        import os
        
        for root, dirs, files in os.walk(path):
            for file in files:
                if file.endswith('pb2.py') and not file.startswith('__'):
                    module_path = Path(root) / file
                    module_name = str(module_path.relative_to(path)).replace(os.sep, '.').replace('.py', '')
                    
                    try:
                        spec = importlib.util.spec_from_file_location(module_name, module_path)
                        if spec and spec.loader:
                            module = importlib.util.module_from_spec(spec)
                            spec.loader.exec_module(module)
                            
                            # Add to descriptor pool
                            if hasattr(module, 'DESCRIPTOR'):
                                desc = module.DESCRIPTOR
                                serialized_desc = desc.serialized_pb
                                file_desc = FileDescriptorProto()
                                file_desc.ParseFromString(serialized_desc)
                                self.descriptor_db.Add(file_desc)
                    except Exception as e:
                        print(f"Warning: Could not load {module_path}: {e}", file=sys.stderr)
    
    def _load_proto_module(self, module_name: str):
        """Load proto definitions from a Python module."""
        try:
            module = importlib.import_module(module_name)
            # Try to find all pb2 modules in the package
            if hasattr(module, '__path__'):
                import pkgutil
                for importer, modname, ispkg in pkgutil.walk_packages(module.__path__, module.__name__ + '.'):
                    if 'pb2' in modname:
                        try:
                            submodule = importlib.import_module(modname)
                            if hasattr(submodule, 'DESCRIPTOR'):
                                desc = submodule.DESCRIPTOR
                                serialized_desc = desc.serialized_pb
                                file_desc = FileDescriptorProto()
                                file_desc.ParseFromString(serialized_desc)
                                self.descriptor_db.Add(file_desc)
                        except Exception as e:
                            pass
        except Exception as e:
            print(f"Warning: Could not load module {module_name}: {e}", file=sys.stderr)
    
    def decode_varint(self, data: bytes, pos: int = 0) -> tuple[Optional[int], int]:
        """Decode a varint from bytes."""
        value = 0
        shift = 0
        start = pos
        max_bytes = 10
        
        while pos < len(data) and shift < 64:
            if pos >= len(data):
                return None, pos
            byte = data[pos]
            value |= (byte & 0x7F) << shift
            pos += 1
            shift += 7
            if not (byte & 0x80):
                return value, pos
            if pos - start >= max_bytes:
                return None, pos
        
        return None, pos
    
    def extract_messages(self, data: bytes, format: str = "auto") -> List[bytes]:
        """Extract protobuf messages from raw data.
        
        Supports:
        - gRPC-web frame format (0x00/0x80 prefix)
        - Varint length prefix
        - Raw protobuf (no prefix)
        """
        messages = []
        
        if format == "auto":
            # Try to detect format
            if len(data) >= 5 and data[0] in (0x00, 0x80):
                format = "grpc-web"
            elif len(data) > 0 and data[0] < 0x80:
                format = "varint"
            else:
                format = "raw"
        
        if format == "grpc-web":
            pos = 0
            while pos < len(data):
                if pos + 5 > len(data):
                    break
                
                frame_type = data[pos]
                frame_len = int.from_bytes(data[pos+1:pos+5], "big")
                
                if frame_type == 0x00:  # Data frame
                    if pos + 5 + frame_len <= len(data):
                        messages.append(data[pos+5:pos+5+frame_len])
                        pos += 5 + frame_len
                    else:
                        break
                elif frame_type == 0x80:  # Skip frame
                    pos += 5 + frame_len
                else:
                    pos += 1
        
        elif format == "varint":
            pos = 0
            while pos < len(data):
                length, offset = self.decode_varint(data, pos)
                if length is None or length == 0:
                    break
                if offset + length <= len(data):
                    messages.append(data[offset:offset+length])
                    pos = offset + length
                else:
                    break
        
        else:  # raw
            messages = [data]
        
        return messages
    
    def decode_with_proto(self, message: bytes, message_type: str) -> Optional[Dict[str, Any]]:
        """Decode message using known proto definition."""
        if not PROTOBUF_AVAILABLE:
            return None
        
        try:
            # Try to find message type in descriptor pool
            descriptor = self.descriptor_pool.FindMessageTypeByName(message_type)
            message_class = message_factory.GetMessageClass(descriptor)
            msg = message_class()
            msg.ParseFromString(message)
            
            # Convert to dict
            return json_format.MessageToDict(msg)
        except Exception as e:
            return None
    
    def decode_with_blackbox(self, message: bytes) -> Dict[str, Any]:
        """Decode message using blackboxprotobuf (no proto definition needed)."""
        if not BLACKBOX_AVAILABLE:
            return {"error": "blackboxprotobuf not available"}
        
        try:
            decoded, typedef = bbp.protobuf_to_json(message)
            return {
                "decoded": json.loads(decoded) if isinstance(decoded, str) else decoded,
                "typedef": typedef
            }
        except Exception as e:
            return {"error": str(e)}
    
    def decode(self, data: bytes, message_type: Optional[str] = None, 
               format: str = "auto", use_blackbox: bool = False) -> Dict[str, Any]:
        """Decode protobuf data.
        
        Args:
            data: Raw protobuf bytes
            message_type: Optional message type name (e.g., "nest.rpc.StreamBody")
            format: Format of data ("auto", "grpc-web", "varint", "raw")
            use_blackbox: Use blackboxprotobuf if proto definition not found
        
        Returns:
            Dictionary with decoded data
        """
        result = {
            "format_detected": format,
            "messages": []
        }
        
        # Extract messages
        messages = self.extract_messages(data, format)
        result["message_count"] = len(messages)
        
        for i, message in enumerate(messages):
            msg_result = {
                "message_index": i,
                "size_bytes": len(message),
                "hex_preview": message[:50].hex() + ("..." if len(message) > 50 else "")
            }
            
            # Try proto-based decoding first
            if message_type:
                decoded = self.decode_with_proto(message, message_type)
                if decoded:
                    msg_result["decoded"] = decoded
                    msg_result["decoder"] = "proto"
            
            # Fall back to blackbox if needed
            if "decoded" not in msg_result and use_blackbox:
                blackbox_result = self.decode_with_blackbox(message)
                if "error" not in blackbox_result:
                    msg_result["decoded"] = blackbox_result.get("decoded")
                    msg_result["typedef"] = blackbox_result.get("typedef")
                    msg_result["decoder"] = "blackbox"
            
            result["messages"].append(msg_result)
        
        return result


def load_data_from_file(file_path: Path, encoding: str = "binary") -> bytes:
    """Load data from file.
    
    Args:
        file_path: Path to file
        encoding: "binary", "hex", or "base64"
    """
    if encoding == "binary":
        return file_path.read_bytes()
    elif encoding == "hex":
        hex_str = file_path.read_text().strip().replace(" ", "").replace("\n", "")
        return bytes.fromhex(hex_str)
    elif encoding == "base64":
        base64_str = file_path.read_text().strip().replace(" ", "").replace("\n", "")
        return base64.b64decode(base64_str)
    else:
        raise ValueError(f"Unknown encoding: {encoding}")


def fetch_data_from_url(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    data: Optional[bytes] = None,
    stream: bool = False,
    timeout: int = 30
) -> bytes:
    """Fetch protobuf data from a URL.
    
    Args:
        url: URL to fetch from
        method: HTTP method (GET, POST, etc.)
        headers: Optional HTTP headers
        data: Optional request body (for POST)
        stream: Whether to stream the response
        timeout: Request timeout in seconds
    
    Returns:
        Response data as bytes
    """
    if not REQUESTS_AVAILABLE:
        raise ImportError("requests library required for URL fetching. Install with: pip install requests")
    
    try:
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            data=data,
            stream=stream,
            timeout=timeout
        )
        response.raise_for_status()
        
        if stream:
            # For streaming, read all chunks
            chunks = []
            for chunk in response.iter_content(chunk_size=None):
                if chunk:
                    chunks.append(chunk)
            return b''.join(chunks)
        else:
            return response.content
    except requests.RequestException as e:
        raise RuntimeError(f"Failed to fetch from URL {url}: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="General-purpose Protobuf Decoder - Decode protobuf messages from any service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Decode a binary file (auto-detect format)
  python proto_decode.py decode file.bin
  
  # Decode from URL (GET request)
  python proto_decode.py decode --url https://api.example.com/protobuf/endpoint
  
  # Decode from URL with authentication
  python proto_decode.py decode --url https://api.example.com/data \
    --headers '{"Authorization": "Bearer token123"}'
  
  # POST request with protobuf payload
  python proto_decode.py decode --url https://api.example.com/observe \
    --method POST \
    --post-data request.bin \
    --headers '{"Content-Type": "application/x-protobuf"}'
  
  # Decode with specific message type
  python proto_decode.py decode file.bin --message-type nest.rpc.StreamBody
  
  # Decode hex string
  python proto_decode.py decode --hex "0a0b48656c6c6f20576f726c64"
  
  # Decode base64
  python proto_decode.py decode --base64 "CgtIZWxsbyBXb3JsZA=="
  
  # Use blackboxprotobuf (no proto definition needed)
  python proto_decode.py decode file.bin --blackbox
  
  # Load custom proto files
  python proto_decode.py decode file.bin --proto-path ./proto
  
  # Specify format explicitly
  python proto_decode.py decode file.bin --format grpc-web
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command")
    
    # Decode command
    decode_parser = subparsers.add_parser("decode", help="Decode protobuf message")
    decode_parser.add_argument(
        "file",
        nargs="?",
        type=Path,
        help="File containing protobuf data (binary, hex, or base64)"
    )
    decode_parser.add_argument(
        "--hex",
        type=str,
        help="Hex string to decode (instead of file)"
    )
    decode_parser.add_argument(
        "--base64",
        type=str,
        help="Base64 string to decode (instead of file)"
    )
    decode_parser.add_argument(
        "--url",
        type=str,
        help="URL to fetch protobuf data from (instead of file)"
    )
    decode_parser.add_argument(
        "--method",
        choices=["GET", "POST", "PUT"],
        default="GET",
        help="HTTP method for URL request (default: GET)"
    )
    decode_parser.add_argument(
        "--headers",
        type=str,
        help="HTTP headers as JSON string (e.g., '{\"Authorization\": \"Bearer token\"}')"
    )
    decode_parser.add_argument(
        "--post-data",
        type=str,
        help="POST data (hex string or base64, or file path)"
    )
    decode_parser.add_argument(
        "--post-data-encoding",
        choices=["hex", "base64", "binary"],
        default="binary",
        help="Encoding for POST data if --post-data is a file (default: binary)"
    )
    decode_parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Request timeout in seconds (default: 30)"
    )
    decode_parser.add_argument(
        "--stream",
        action="store_true",
        help="Stream the response (for large responses)"
    )
    decode_parser.add_argument(
        "--message-type",
        type=str,
        help="Protobuf message type name (e.g., 'nest.rpc.StreamBody')"
    )
    decode_parser.add_argument(
        "--format",
        choices=["auto", "grpc-web", "varint", "raw"],
        default="auto",
        help="Data format (default: auto-detect)"
    )
    decode_parser.add_argument(
        "--encoding",
        choices=["binary", "hex", "base64"],
        default="binary",
        help="File encoding if reading from file (default: binary)"
    )
    decode_parser.add_argument(
        "--proto-path",
        type=Path,
        help="Path to directory containing .proto or pb2.py files"
    )
    decode_parser.add_argument(
        "--proto-module",
        type=str,
        help="Python module name containing proto definitions (e.g., 'proto.nest.rpc')"
    )
    decode_parser.add_argument(
        "--blackbox",
        action="store_true",
        help="Use blackboxprotobuf if proto definition not found"
    )
    decode_parser.add_argument(
        "--output",
        choices=["json", "pretty"],
        default="pretty",
        help="Output format (default: pretty)"
    )
    
    # Info command
    info_parser = subparsers.add_parser("info", help="Show decoder information")
    info_parser.add_argument(
        "--proto-path",
        type=Path,
        help="Path to directory containing proto files"
    )
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    if args.command == "decode":
        # Load data
        if args.url:
            # Fetch from URL
            try:
                headers = None
                if args.headers:
                    try:
                        headers = json.loads(args.headers)
                    except json.JSONDecodeError as e:
                        print(f"Error: Invalid JSON in --headers: {e}", file=sys.stderr)
                        return 1
                
                post_data = None
                if args.post_data:
                    # Check if it's a file path
                    post_data_path = Path(args.post_data)
                    if post_data_path.exists():
                        post_data = load_data_from_file(post_data_path, args.post_data_encoding)
                    else:
                        # Try as hex or base64 string
                        try:
                            # Try hex first
                            post_data = bytes.fromhex(args.post_data.replace(" ", "").replace("\n", ""))
                        except ValueError:
                            try:
                                # Try base64
                                post_data = base64.b64decode(args.post_data.replace(" ", "").replace("\n", ""))
                            except Exception as e:
                                print(f"Error: Could not parse --post-data as hex, base64, or file: {e}", file=sys.stderr)
                                return 1
                
                data = fetch_data_from_url(
                    args.url,
                    method=args.method,
                    headers=headers,
                    data=post_data,
                    stream=args.stream,
                    timeout=args.timeout
                )
            except Exception as e:
                print(f"Error fetching from URL: {e}", file=sys.stderr)
                return 1
        elif args.hex:
            try:
                hex_str = args.hex.replace(" ", "").replace("\n", "")
                data = bytes.fromhex(hex_str)
            except ValueError as e:
                print(f"Error: Invalid hex string: {e}", file=sys.stderr)
                return 1
        elif args.base64:
            try:
                base64_str = args.base64.replace(" ", "").replace("\n", "")
                data = base64.b64decode(base64_str)
            except Exception as e:
                print(f"Error: Invalid base64 string: {e}", file=sys.stderr)
                return 1
        elif args.file:
            if not args.file.exists():
                print(f"Error: File not found: {args.file}", file=sys.stderr)
                return 1
            try:
                data = load_data_from_file(args.file, args.encoding)
            except Exception as e:
                print(f"Error loading file: {e}", file=sys.stderr)
                return 1
        else:
            print("Error: Must provide file, --url, --hex, or --base64", file=sys.stderr)
            return 1
        
        # Initialize decoder
        decoder = ProtoDecoder(
            proto_path=args.proto_path or Path("proto"),
            proto_module=args.proto_module
        )
        
        # Decode
        result = decoder.decode(
            data,
            message_type=args.message_type,
            format=args.format,
            use_blackbox=args.blackbox
        )
        
        # Output
        if args.output == "json":
            print(json.dumps(result, indent=2))
        else:
            _print_pretty(result)
    
    elif args.command == "info":
        decoder = ProtoDecoder(
            proto_path=args.proto_path or Path("proto"),
            proto_module=None
        )
        print("Protobuf Decoder Information")
        print("=" * 50)
        print(f"Protobuf available: {PROTOBUF_AVAILABLE}")
        print(f"Blackboxprotobuf available: {BLACKBOX_AVAILABLE}")
        if decoder.proto_path:
            print(f"Proto path: {decoder.proto_path}")
        if decoder.proto_module:
            print(f"Proto module: {decoder.proto_module}")
    
    return 0


def _print_pretty(result: Dict[str, Any]):
    """Print decoded result in a pretty format."""
    print("=" * 80)
    print("PROTOBUF DECODER RESULTS")
    print("=" * 80)
    print()
    
    print(f"Format: {result.get('format_detected', 'unknown')}")
    print(f"Messages found: {result.get('message_count', 0)}")
    print()
    
    for msg in result.get("messages", []):
        print(f"Message {msg.get('message_index', 0)}:")
        print(f"  Size: {msg.get('size_bytes', 0)} bytes")
        print(f"  Hex preview: {msg.get('hex_preview', 'N/A')}")
        
        if "decoded" in msg:
            print(f"  Decoder: {msg.get('decoder', 'unknown')}")
            print(f"  Decoded data:")
            decoded = msg["decoded"]
            if isinstance(decoded, dict):
                print(json.dumps(decoded, indent=4))
            else:
                print(f"    {decoded}")
        
        if "typedef" in msg:
            print(f"  Type definition:")
            print(json.dumps(msg["typedef"], indent=4))
        
        print()


if __name__ == "__main__":
    sys.exit(main())

