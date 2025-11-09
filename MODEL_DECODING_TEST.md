# Model Decoding Test Guide

## Overview

This guide helps verify that the model field ("Next x Yale Lock-1.1") is correctly decoded from the `DeviceIdentityTrait` protobuf message.

## Test Script

Run the dedicated test script:

```bash
cd yalenestlocktest
source .venv/bin/activate
python test_model_decoding.py
```

This script will:
1. Connect to the Nest Observe stream
2. Request `DeviceIdentityTrait` specifically
3. Decode all received messages
4. Report whether the model field was found and its value
5. Provide detailed debugging information if the model is missing

## Expected Output

### Success Case:
```
✅ Model found in DeviceIdentityTrait: 'Next x Yale Lock-1.1'
✅ MODEL: Next x Yale Lock-1.1
✅ Model matches expected pattern!
```

### Failure Case:
```
⚠️  model_name field not present in DeviceIdentityTrait
❌ MODEL: NOT FOUND
```

## What Was Fixed

### 1. Enhanced Logging
- Added detailed logging when model is found/not found
- Logs whether `model_name` field exists but is empty
- Includes model value in the main DeviceIdentityTrait decode log

### 2. Improved Error Detection
- Checks if `HasField("model_name")` returns True
- Checks if the value is non-empty after extraction
- Provides specific warnings for each failure case

### 3. Test Script
- Created `test_model_decoding.py` specifically for model testing
- Focuses only on DeviceIdentityTrait to reduce noise
- Provides clear pass/fail indication

## Proto Definition

The model is defined in `proto/weave/trait/description.proto`:

```protobuf
message DeviceIdentityTrait {
  String_Indirect manufacturer = 2;
  String_Indirect model_name = 4;  // This is field 4
  string serial_number = 6;
  string fw_version = 7;
}
```

The model is accessed via:
- `trait.HasField("model_name")` - checks if field is present
- `trait.model_name.value` - gets the actual string value

## Debugging Steps

If the model is not being decoded:

1. **Check if DeviceIdentityTrait is being requested:**
   ```python
   # In observe payload
   "weave.trait.description.DeviceIdentityTrait"
   ```

2. **Check if the field exists in the message:**
   - Look for log: `⚠️  model_name field not present`
   - This means the field isn't in the protobuf message

3. **Check if the field is empty:**
   - Look for log: `⚠️  model_name field exists but value is empty`
   - This means the field exists but has no value

4. **Verify proto file:**
   - Check `proto/weave/trait/description_pb2.py` exists
   - Verify it has `model_name` field (field 4)

5. **Check raw protobuf data:**
   - Enable DEBUG logging to see hex dumps
   - Compare with known working captures

## Integration with HA

Once model decoding is verified in the test project:

1. The same code pattern is used in `ha-nest-yale-integration`
2. Model is extracted in `protobuf_handler.py`
3. Model is stored in `all_traits` dictionary
4. Model is accessed via `get_device_metadata()` in `api_client.py`
5. Model is used in `lock.py` for device info

## Files Modified

- `protobuf_handler_enhanced.py` - Added detailed model logging
- `protobuf_handler.py` - Added detailed model logging  
- `test_model_decoding.py` - New test script for model verification

