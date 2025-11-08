#!/usr/bin/env python3
"""
Simple hex message decoder - extracts IDs directly from hex string.
"""

import sys
import binascii
import re


def decode_hex_message(hex_string: str):
    """Decode hex and extract IDs."""
    # Remove whitespace
    hex_string = hex_string.replace(" ", "").replace("\n", "")
    
    # Convert hex to bytes
    try:
        raw_bytes = binascii.unhexlify(hex_string)
    except binascii.Error as e:
        print(f"Error: Invalid hex string: {e}", file=sys.stderr)
        return None
    
    print(f"Message length: {len(raw_bytes)} bytes")
    print("=" * 80)
    
    # Convert to string to search for IDs
    try:
        text = raw_bytes.decode('utf-8', errors='ignore')
    except:
        text = str(raw_bytes)
    
    # Also search in hex representation
    hex_text = raw_bytes.hex()
    
    # Extract IDs using patterns
    structure_ids = set()
    user_ids = set()
    device_ids = set()
    
    # Look for STRUCTURE_XXXXX pattern
    structure_pattern = rb'STRUCTURE_([A-F0-9]{16})'
    matches = re.findall(structure_pattern, raw_bytes)
    for match in matches:
        structure_ids.add(match.decode('ascii'))
    
    # Also try case-insensitive
    structure_pattern_ci = rb'[Ss][Tt][Rr][Uu][Cc][Tt][Uu][Rr][Ee]_([A-F0-9]{16})'
    matches = re.findall(structure_pattern_ci, raw_bytes, re.IGNORECASE)
    for match in matches:
        structure_ids.add(match.decode('ascii'))
    
    # Look for USER_XXXXX pattern
    user_pattern = rb'USER_([A-F0-9]{16})'
    matches = re.findall(user_pattern, raw_bytes)
    for match in matches:
        user_ids.add(match.decode('ascii'))
    
    # Look for DEVICE_XXXXX pattern
    device_pattern = rb'DEVICE_([A-F0-9]{16})'
    matches = re.findall(device_pattern, raw_bytes)
    for match in matches:
        device_ids.add(match.decode('ascii'))
    
    # Also search for ASCII strings directly
    if b'STRUCTURE_' in raw_bytes:
        idx = raw_bytes.find(b'STRUCTURE_')
        if idx != -1:
            struct_part = raw_bytes[idx:idx+26]  # STRUCTURE_ + 16 hex chars
            if len(struct_part) >= 26:
                struct_id = struct_part[10:26].decode('ascii', errors='ignore')
                if len(struct_id) == 16:
                    structure_ids.add(struct_id)
    
    if b'USER_' in raw_bytes:
        idx = raw_bytes.find(b'USER_')
        if idx != -1:
            user_part = raw_bytes[idx:idx+21]  # USER_ + 16 hex chars
            if len(user_part) >= 21:
                user_id = user_part[5:21].decode('ascii', errors='ignore')
                if len(user_id) == 16:
                    user_ids.add(user_id)
    
    if b'DEVICE_' in raw_bytes:
        idx = raw_bytes.find(b'DEVICE_')
        if idx != -1:
            device_part = raw_bytes[idx:idx+23]  # DEVICE_ + 16 hex chars
            if len(device_part) >= 23:
                device_id = device_part[7:23].decode('ascii', errors='ignore')
                if len(device_id) == 16:
                    device_ids.add(device_id)
    
    # Print results
    print("\n📋 EXTRACTED IDs:")
    print("-" * 80)
    
    if structure_ids:
        print(f"\n✅ Structure IDs found: {len(structure_ids)}")
        for sid in sorted(structure_ids):
            print(f"   - {sid}")
    else:
        print("\n❌ Structure ID: NOT FOUND")
    
    if user_ids:
        print(f"\n✅ User IDs found: {len(user_ids)}")
        for uid in sorted(user_ids):
            print(f"   - {uid}")
    else:
        print("\n❌ User ID: NOT FOUND")
    
    if device_ids:
        print(f"\n✅ Device IDs found: {len(device_ids)}")
        for did in sorted(device_ids):
            print(f"   - DEVICE_{did}")
    else:
        print("\n❌ Device ID: NOT FOUND")
    
    # Show raw bytes in readable format
    print("\n" + "=" * 80)
    print("📄 MESSAGE CONTENT (readable ASCII parts):")
    print("-" * 80)
    
    # Find all readable ASCII sequences
    readable_parts = []
    current_seq = bytearray()
    
    for byte in raw_bytes:
        if 32 <= byte <= 126:  # Printable ASCII
            current_seq.append(byte)
        else:
            if len(current_seq) >= 4:  # Only show sequences of 4+ chars
                readable_parts.append(current_seq.decode('ascii'))
            current_seq = bytearray()
    
    if len(current_seq) >= 4:
        readable_parts.append(current_seq.decode('ascii'))
    
    for part in readable_parts[:20]:  # Show first 20 readable parts
        if any(keyword in part for keyword in ['STRUCTURE', 'USER', 'DEVICE', 'bolt', 'trait', 'resource']):
            print(f"   {part}")
    
    return {
        "structure_ids": list(structure_ids),
        "user_ids": list(user_ids),
        "device_ids": list(device_ids),
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python decode_hex_simple.py <hex_string>")
        return 1
    
    hex_string = sys.argv[1]
    decode_hex_message(hex_string)
    return 0


if __name__ == "__main__":
    sys.exit(main())

