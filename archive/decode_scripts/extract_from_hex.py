#!/usr/bin/env python3
"""
Extract HomeKit information from hex-encoded protobuf messages.
"""

import binascii
import sys

# From the capture output, we can extract the serial number directly
hex_serial = "41484e4a32303035323938"
serial = binascii.unhexlify(hex_serial).decode('utf-8')

hex_fw = "312e322d37"
fw = binascii.unhexlify(hex_fw).decode('utf-8')

print("="*80)
print("HOMEKIT INFORMATION EXTRACTED FROM CAPTURE")
print("="*80)
print()
print(f"✅ Serial Number: {serial}")
print(f"✅ Firmware Version: {fw}")
print()
print("This information was found in the DeviceIdentityTrait message.")
print()
print("The protobuf_handler currently doesn't decode DeviceIdentityTrait,")
print("but the data is present in the messages. To extract it automatically,")
print("you need to add DeviceIdentityTrait decoding to protobuf_handler.py")
print("as shown in homekit_protobuf_patch.py")

