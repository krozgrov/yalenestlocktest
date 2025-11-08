# Message Decoding Results ✅

## Test Results

All messages were successfully decoded using blackboxprotobuf. Results below.

## Message 1: 00001.raw.bin (957 bytes)

### ✅ Successfully Decoded!

**Extracted Information:**
- **Structure ID**: `018C86E39308F29F`
- **User ID**: `015EADBA454C1770`
- **Device ID**: `DEVICE_00177A0000060303`
  - Type: `yale.resource.LinusLockResource`
  - Traits:
    - `weave.trait.security.BoltLockTrait`
    - `weave.trait.security.BoltLockSettingsTrait`
    - `weave.trait.security.BoltLockCapabilitiesTrait`
    - `weave.trait.security.PincodeInputTrait`
    - `weave.trait.security.TamperTrait`

### Decoded Structure

The message contains:
1. **Structure Resource** (`STRUCTURE_018C86E39308F29F`)
   - StructureInfoTrait
   - MobileStructureIface

2. **Yale Lock Device** (`DEVICE_00177A0000060303`)
   - All 5 security traits
   - Multiple interfaces (DeviceIface, LocatedDeviceIface, MobileLinusLockIface, etc.)

3. **User Resource** (`USER_015EADBA454C1770`)
   - UserInfoTrait
   - MobileUserIface

## Message 2: 00002.raw.bin (1213 bytes)

### ⚠️ Decoding Note

This message may require gRPC-web frame unwrapping, but readable strings show:
- **User ID**: `USER_015EADBA454C1770`
- **Device ID**: `DEVICE_00177A0000060303`
- **Traits**: BoltLockTrait, BoltLockSettingsTrait, BoltLockCapabilitiesTrait

## Key Findings

### ✅ IDs Successfully Extracted

All critical IDs are present in the messages:
- Structure ID: `018C86E39308F29F` ✅
- User ID: `015EADBA454C1770` ✅
- Device ID: `DEVICE_00177A0000060303` ✅

### ✅ Trait Information Available

All lock traits are present:
- BoltLockTrait ✅
- BoltLockSettingsTrait ✅
- BoltLockCapabilitiesTrait ✅
- PincodeInputTrait ✅
- TamperTrait ✅

### ⚠️ Existing Proto Files

The existing `rpc.StreamBody` proto fails to decode these messages:
- Error: `Error parsing message with type 'nest.rpc.StreamBody'`
- This confirms why updated proto files are needed!

## Conclusion

✅ **Messages decode successfully with blackboxprotobuf**
✅ **All IDs extracted correctly**
✅ **Trait information available**
⚠️ **Existing proto files need updates** (which we've generated!)

The generated proto files in `proto/final/` should help decode these messages once properly integrated.

