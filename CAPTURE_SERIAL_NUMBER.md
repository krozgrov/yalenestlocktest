# Capturing Serial Number and HomeKit Information

Your serial number is **`AHNJ2005298`**, which is different from the device ID format we've been seeing (`DEVICE_00177A0000060303`).

## Why We Need to Capture

The serial number appears in the `DeviceIdentityTrait` message, which we haven't captured yet. The current captures only include lock-related traits, not device identity information.

## How to Capture

### Option 1: Use the Automated Script

```bash
# Activate your virtual environment
source .venv/bin/activate

# Capture with HomeKit traits (includes DeviceIdentityTrait)
python capture_homekit_traits.py
```

This will:
- Request `DeviceIdentityTrait` (contains serial number in field 6)
- Request `BatteryPowerSourceTrait` (contains battery information)
- Save all messages to a new capture directory

### Option 2: Manual Capture

If you want to capture just the serial number:

```python
from reverse_engineering import capture_observe_stream

# Capture with DeviceIdentityTrait
capture_observe_stream(
    traits=[
        "weave.trait.description.DeviceIdentityTrait",  # Serial, firmware, model
        "weave.trait.security.BoltLockTrait",  # Keep existing lock traits
        "nest.trait.structure.StructureInfoTrait",
        "nest.trait.user.UserInfoTrait",
    ],
    output_dir=Path("captures"),
    limit=5,
    capture_blackbox=True,
)
```

## What You'll Get

After capturing with `DeviceIdentityTrait`, you'll find:

- **Serial Number** (`AHNJ2005298`) in field 6
- **Firmware Version** in field 7
- **Manufacturer** in field 2 (String_Indirect)
- **Model Name** in field 4 (String_Indirect)

## Verify the Capture

After capturing, verify your serial number was captured:

```bash
# Search for your serial number
python find_serial_number.py AHNJ2005298

# Or extract all HomeKit info
python extract_all_homekit_data.py --captures-dir captures
```

## Expected Output

When you decode the `DeviceIdentityTrait`, you should see:

```json
{
  "serial_number": "AHNJ2005298",
  "firmware_version": "...",
  "manufacturer": "Yale",
  "model": "Linus Lock"
}
```

## Integration Notes

- The serial number will be in `DeviceIdentityTrait` field 6
- Device ID (`DEVICE_00177A0000060303`) is different from serial number
- Both are useful: device ID for API calls, serial number for HomeKit/display

