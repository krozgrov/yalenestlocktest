#!/usr/bin/env python3
"""
Enhanced tool to update proto files from captures and generate pb2 files.

This tool:
1. Reads typedefs from captures
2. Generates/updates proto files
3. Compiles them to pb2.py files
4. Can merge with existing proto files
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List

# Import the existing generation functions
try:
    from tools.generate_proto import load_typedefs, write_proto, run_protoc
    TOOLS_AVAILABLE = True
except ImportError:
    TOOLS_AVAILABLE = False
    print("Warning: tools/generate_proto.py not found. Using basic generation.", file=sys.stderr)


def merge_typedefs(typedef_files: List[Path]) -> Dict[str, Any]:
    """Merge multiple typedef files into one."""
    merged = {}
    
    for typedef_file in typedef_files:
        try:
            with open(typedef_file, "r", encoding="utf-8") as f:
                typedef = json.load(f)
            
            # Merge logic: take the union of all fields
            def merge_dict(base: Dict, new: Dict, path: str = ""):
                for key, value in new.items():
                    if key in base:
                        if isinstance(base[key], dict) and isinstance(value, dict):
                            merge_dict(base[key], value, f"{path}.{key}")
                        elif isinstance(base[key], list) and isinstance(value, list):
                            # Merge lists (union)
                            base[key] = list(set(base[key] + value))
                        # Otherwise keep the existing value
                    else:
                        base[key] = value
            
            merge_dict(merged, typedef)
        except Exception as e:
            print(f"Warning: Failed to load {typedef_file}: {e}", file=sys.stderr)
    
    return merged


def generate_proto_from_capture(
    capture_dir: Path,
    message_name: str = "StreamBodyMessage",
    proto_root: Path = Path("proto/autogen"),
    python_out: Path = None,
    skip_protoc: bool = False,
):
    """Generate proto files from a capture directory."""
    capture_dir = Path(capture_dir)
    
    if not capture_dir.exists():
        print(f"Error: Capture directory does not exist: {capture_dir}", file=sys.stderr)
        return 1
    
    # Find typedef files
    typedef_files = sorted(capture_dir.glob("*.typedef.json"))
    
    if not typedef_files:
        print(f"Error: No typedef files found in {capture_dir}", file=sys.stderr)
        print("Hint: Run reverse_engineering.py with --no-blackbox=false to generate typedefs", file=sys.stderr)
        return 1
    
    print(f"Found {len(typedef_files)} typedef file(s)")
    
    # Merge typedefs
    if TOOLS_AVAILABLE:
        merged = load_typedefs(typedef_files)
    else:
        merged = merge_typedefs(typedef_files)
    
    # Generate proto file
    proto_root = Path(proto_root).resolve()
    proto_root.mkdir(parents=True, exist_ok=True)
    
    if TOOLS_AVAILABLE:
        proto_path = write_proto(proto_root, message_name, merged)
    else:
        # Basic proto generation
        proto_path = proto_root / f"{message_name.lower()}.proto"
        proto_content = typedef_to_proto(merged, message_name)
        proto_path.write_text(proto_content, encoding="utf-8")
        print(f"Generated proto file: {proto_path}")
    
    # Compile with protoc
    if not skip_protoc:
        python_out = Path(python_out).resolve() if python_out else proto_root
        python_out.mkdir(parents=True, exist_ok=True)
        
        if TOOLS_AVAILABLE:
            run_protoc(proto_path, proto_root, python_out, "protoc")
        else:
            # Basic protoc call
            try:
                subprocess.run(
                    [
                        "protoc",
                        f"--proto_path={proto_root}",
                        f"--python_out={python_out}",
                        str(proto_path.relative_to(proto_root)),
                    ],
                    check=True,
                )
                print(f"Compiled to: {python_out}")
            except subprocess.CalledProcessError as e:
                print(f"Error: protoc failed: {e}", file=sys.stderr)
                print("Hint: Install protoc with: brew install protobuf (macOS) or apt-get install protobuf-compiler (Linux)", file=sys.stderr)
                return 1
            except FileNotFoundError:
                print("Error: protoc not found. Install it or use --skip-protoc", file=sys.stderr)
                return 1
    
    print(f"\n✅ Success!")
    print(f"   Proto file: {proto_path}")
    if not skip_protoc:
        print(f"   Python bindings: {python_out}")
    
    return 0


def typedef_to_proto(typedef: Dict[str, Any], message_name: str, depth: int = 0) -> str:
    """Convert typedef to proto syntax (basic version)."""
    indent = "  " * depth
    lines = []
    
    if depth == 0:
        lines.append("syntax = \"proto3\";")
        lines.append("")
    
    lines.append(f"{indent}message {message_name} {{")
    
    # Sort fields by number
    try:
        field_items = sorted(typedef.items(), key=lambda x: int(x[0]) if str(x[0]).isdigit() else 0)
    except:
        field_items = list(typedef.items())
    
    nested_messages = []
    
    for field_num, field_info in field_items:
        if not isinstance(field_info, dict):
            continue
        
        field_name = field_info.get("name") or f"field_{field_num}"
        field_type = field_info.get("type", "bytes")
        repeated = field_info.get("repeated", False)
        
        # Handle nested messages
        if field_type == "message" and "message_typedef" in field_info:
            nested_name = f"{message_name}Field{field_num}"
            nested_messages.append((nested_name, field_info["message_typedef"]))
            resolved_type = nested_name
        else:
            # Map types
            type_map = {
                "int": "int64",
                "int32": "int32",
                "int64": "int64",
                "uint": "uint64",
                "uint32": "uint32",
                "uint64": "uint64",
                "bool": "bool",
                "string": "string",
                "bytes": "bytes",
                "float": "float",
                "double": "double",
            }
            resolved_type = type_map.get(field_type, "bytes")
        
        label = "repeated " if repeated else ""
        lines.append(f"{indent}  {label}{resolved_type} {field_name} = {field_num};")
    
    lines.append(f"{indent}}}")
    
    # Add nested messages
    for nested_name, nested_typedef in nested_messages:
        lines.append("")
        lines.append(typedef_to_proto(nested_typedef, nested_name, depth))
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Generate proto files from captured protobuf messages"
    )
    parser.add_argument(
        "capture_dir",
        type=Path,
        help="Directory containing captured messages with typedef.json files",
    )
    parser.add_argument(
        "--message-name",
        default="StreamBodyMessage",
        help="Name for the generated message (default: StreamBodyMessage)",
    )
    parser.add_argument(
        "--proto-root",
        type=Path,
        default=Path("proto/autogen"),
        help="Directory for generated proto files (default: proto/autogen)",
    )
    parser.add_argument(
        "--python-out",
        type=Path,
        default=None,
        help="Directory for generated pb2.py files (default: same as proto-root)",
    )
    parser.add_argument(
        "--skip-protoc",
        action="store_true",
        help="Generate proto file but skip compiling with protoc",
    )
    
    args = parser.parse_args()
    
    return generate_proto_from_capture(
        args.capture_dir,
        args.message_name,
        args.proto_root,
        args.python_out,
        args.skip_protoc,
    )


if __name__ == "__main__":
    sys.exit(main())

