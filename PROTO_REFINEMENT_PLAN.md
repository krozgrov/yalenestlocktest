# Proto Refinement Plan

## Problem

The `DecodeError in StreamBody` occurs because:
1. Proto files were reverse-engineered from Nest API v1
2. We're using Nest API v2 (Observe endpoint)
3. The proto definitions are incomplete/mismatched

## Solution Path

### Step 1: Capture Fresh Data ✅
- Use `reverse_engineering.py` to capture Observe responses
- Include all HomeKit-relevant traits
- Generate typedef.json and pseudo.proto files

### Step 2: Analyze Structure
- Extract actual protobuf messages from varint-prefixed chunks
- Use blackboxprotobuf to decode structure
- Compare with existing proto definitions

### Step 3: Identify Gaps
- Find missing fields in StreamBody, NestMessage, TraitGetProperty, etc.
- Identify incorrect field types
- Note nested message structure differences

### Step 4: Update Proto Files
- Manually update proto/nest/rpc.proto based on typedef analysis
- Ensure all fields from API v2 are included
- Fix field types and nested structures

### Step 5: Regenerate pb2.py
- Compile updated proto files
- Test that StreamBody parsing works
- Verify all traits decode successfully

### Step 6: Test in Test Project
- Verify all trait decoders work
- Test with live Observe stream
- Confirm no DecodeErrors

### Step 7: Integration
- Only after everything works in test project
- Copy updated proto files to HA project
- Regenerate pb2.py files in HA project
- Update protobuf_handler.py in HA project

## Current Status

- ✅ Enhanced protobuf_handler.py with DeviceIdentityTrait and BatteryPowerSourceTrait decoders
- ✅ Handler successfully processes some messages (seen in test output)
- ⚠️ Some messages fail with DecodeError (incomplete proto definitions)
- ⚠️ Need to refine proto/nest/rpc.proto based on blackboxprotobuf output

## Next Steps

1. Analyze message 18 (462 bytes) which contains DeviceIdentityTrait
2. Compare its structure with existing StreamBody proto
3. Update proto files to match API v2 structure
4. Regenerate and test

