#!/usr/bin/env python3
"""
Extract protobuf messages from gRPC-web format.

The raw.bin files contain gRPC-web formatted responses that need to be
parsed to extract the actual protobuf messages.
"""

from pathlib import Path
from typing import List


def decode_varint(buffer: bytes, pos: int) -> tuple[int | None, int]:
    """Decode a varint from buffer starting at pos."""
    value = 0
    shift = 0
    start = pos
    max_bytes = 10
    
    while pos < len(buffer) and shift < 64:
        byte = buffer[pos]
        value |= (byte & 0x7F) << shift
        pos += 1
        shift += 7
        if not (byte & 0x80):
            return value, pos
        if pos - start >= max_bytes:
            return None, pos
    
    return None, start


def extract_protobuf_messages(raw_data: bytes) -> List[bytes]:
    """Extract all protobuf messages from gRPC-web format."""
    messages = []
    pos = 0
    
    while pos < len(raw_data):
        # Check for gRPC-web frame format (0x00 or 0x80)
        if pos + 5 <= len(raw_data) and raw_data[pos] in (0x00, 0x80):
            frame_type = raw_data[pos]
            frame_len = int.from_bytes(raw_data[pos + 1:pos + 5], "big")
            
            if frame_type == 0x80:
                # Skip frame
                pos += 5 + frame_len
                continue
            
            if frame_len == 0:
                pos += 5
                continue
            
            if pos + 5 + frame_len <= len(raw_data):
                message = raw_data[pos + 5:pos + 5 + frame_len]
                messages.append(message)
                pos += 5 + frame_len
            else:
                # Incomplete frame
                break
        
        # Try varint length prefix
        else:
            length, new_pos = decode_varint(raw_data, pos)
            if length is None or length == 0:
                # No valid varint, try to parse remaining as message
                if pos < len(raw_data):
                    messages.append(raw_data[pos:])
                break
            
            if new_pos + length <= len(raw_data):
                message = raw_data[new_pos:new_pos + length]
                messages.append(message)
                pos = new_pos + length
            else:
                # Incomplete message
                break
    
    return messages


def test_extraction(capture_file: Path):
    """Test extracting messages from a capture file."""
    print(f"Testing: {capture_file.name}")
    
    with open(capture_file, "rb") as f:
        raw_data = f.read()
    
    print(f"  Raw data length: {len(raw_data)} bytes")
    
    messages = extract_protobuf_messages(raw_data)
    
    print(f"  Extracted {len(messages)} message(s)")
    
    for i, msg in enumerate(messages, 1):
        print(f"    Message {i}: {len(msg)} bytes")
        print(f"      First 50 bytes (hex): {msg[:50].hex()}")
    
    return messages


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        capture_file = Path(sys.argv[1])
    else:
        # Use latest capture
        captures_dir = Path("captures")
        capture_dirs = sorted([d for d in captures_dir.iterdir() if d.is_dir()],
                            key=lambda x: x.stat().st_mtime, reverse=True)
        if not capture_dirs:
            print("Error: No captures found")
            sys.exit(1)
        capture_file = capture_dirs[0] / "00001.raw.bin"
    
    if not capture_file.exists():
        print(f"Error: File not found: {capture_file}")
        sys.exit(1)
    
    test_extraction(capture_file)

