I # HomeKit Information Extraction Guide

This guide shows how to extract HomeKit-relevant information (serial numbers, battery, firmware, etc.) from Nest protobuf messages and integrate it into your Home Assistant project.

## Available Information

### Currently Available (from existing captures):
- ⚠️ **Serial Number**: Not found in current captures (needs `DeviceIdentityTrait`)
  - Note: Device ID (`DEVICE_00177A0000060303`) is different from serial number (`AHNJ2005298`)
  - Serial number appears in `DeviceIdentityTrait` field 6
- ⚠️ **Battery**: Partial data found, but needs `BatteryPowerSourceTrait` for complete info
- ⚠️ **Firmware**: Not found in current captures (needs `DeviceIdentityTrait`)
- ✅ **Timestamps**: Found in messages (can indicate last contact)
- ⚠️ **Model/Manufacturer**: Partial (from resource type, needs `DeviceIdentityTrait` for full info)

### Required Traits for Full HomeKit Support:

1. **`weave.trait.description.DeviceIdentityTrait`**
   - Serial number (field 6)
   - Firmware version (field 7)
   - Manufacturer (field 2)
   - Model name (field 4)

2. **`weave.trait.power.BatteryPowerSourceTrait`**
   - Battery remaining percent (field 33.1)
   - Battery replacement indicator (field 32)
   - Voltage (field 2)
   - Condition/Status (fields 5, 6)

3. **`weave.trait.power.PowerSourceTrait`** (alternative)
   - Power status
   - Voltage/Current

## Quick Start

### 1. Extract Current Information

```bash
# Extract what's available from existing captures
python extract_all_homekit_data.py --captures-dir captures

# Output shows:
# - Serial numbers found
# - Battery info (if any)
# - Timestamps
# - What's missing
```

### 2. Capture with HomeKit Traits

```bash
# Capture messages with DeviceIdentityTrait and PowerTrait
python capture_homekit_traits.py

# This will create a new capture directory with:
# - DeviceIdentityTrait (serial, firmware, model)
# - PowerTrait (battery info)
```

### 3. Extract Full HomeKit Data

```bash
# After capturing, extract all HomeKit info
python extract_all_homekit_data.py --capture-dir captures/[latest_dir]

# Or decode using proto files
python decode_homekit_info.py captures/[latest_dir]/*.raw.bin
```

## Integration into Home Assistant

### Step 1: Update Observe Payload

In `api_client.py`, add HomeKit-relevant traits to the observe payload:

```python
def _build_observe_payload(self):
    request = v2_pb2.ObserveRequest(version=2, subscribe=True)
    trait_names = [
        # Existing traits
        "nest.trait.user.UserInfoTrait",
        "nest.trait.structure.StructureInfoTrait",
        "weave.trait.security.BoltLockTrait",
        "weave.trait.security.BoltLockSettingsTrait",
        "weave.trait.security.BoltLockCapabilitiesTrait",
        "weave.trait.security.PincodeInputTrait",
        "weave.trait.security.TamperTrait",
        # Add HomeKit traits
        "weave.trait.description.DeviceIdentityTrait",  # Serial, firmware, model
        "weave.trait.power.BatteryPowerSourceTrait",    # Battery level, status
    ]
    for trait in trait_names:
        observe_filter = request.filter.add()
        observe_filter.trait_type = trait
    return request.SerializeToString()
```

### Step 2: Update Protobuf Handler

Add methods to extract HomeKit information in `protobuf_handler.py`:

```python
def _extract_homekit_info(self, get_op, property_any, obj_id):
    """Extract HomeKit-relevant information from traits."""
    homekit_info = {}
    type_url = getattr(property_any, "type_url", None) if property_any else None
    
    # DeviceIdentityTrait
    if "DeviceIdentityTrait" in (type_url or ""):
        try:
            from .proto.weave.trait import description_pb2
            identity = description_pb2.DeviceIdentityTrait()
            property_any.Unpack(identity)
            
            if identity.serial_number:
                homekit_info["serial_number"] = identity.serial_number
            if identity.fw_version:
                homekit_info["firmware_version"] = identity.fw_version
            if identity.HasField("manufacturer"):
                homekit_info["manufacturer"] = identity.manufacturer.value
            if identity.HasField("model_name"):
                homekit_info["model"] = identity.model_name.value
        except Exception as e:
            _LOGGER.debug("Failed to extract DeviceIdentityTrait: %s", e)
    
    # BatteryPowerSourceTrait
    elif "BatteryPowerSourceTrait" in (type_url or ""):
        try:
            from .proto.weave.trait import power_pb2
            battery = power_pb2.BatteryPowerSourceTrait()
            property_any.Unpack(battery)
            
            if battery.HasField("remaining") and battery.remaining.HasField("remainingPercent"):
                homekit_info["battery_level"] = battery.remaining.remainingPercent.value
            if battery.replacementIndicator:
                homekit_info["battery_replacement_indicator"] = battery.replacementIndicator
            if battery.HasField("assessedVoltage"):
                homekit_info["battery_voltage"] = battery.assessedVoltage.value
            if battery.condition:
                homekit_info["battery_condition"] = battery.condition
            if battery.status:
                homekit_info["battery_status"] = battery.status
        except Exception as e:
            _LOGGER.debug("Failed to extract BatteryPowerSourceTrait: %s", e)
    
    return homekit_info
```

### Step 3: Integrate into Message Processing

Update `_process_message` to extract and include HomeKit info:

```python
async def _process_message(self, message):
    # ... existing code ...
    
    for msg in self.stream_body.message:
        for get_op in msg.get:
            # ... existing trait processing ...
            
            # Extract HomeKit info
            if property_any:
                homekit_info = self._extract_homekit_info(get_op, property_any, obj_id)
                if homekit_info and obj_id:
                    if obj_id not in locks_data["yale"]:
                        locks_data["yale"][obj_id] = {}
                    locks_data["yale"][obj_id].update(homekit_info)
            
            # Also extract serial from device ID if not found
            if obj_id and obj_id.startswith("DEVICE_"):
                serial = obj_id.replace("DEVICE_", "")
                if obj_id not in locks_data["yale"]:
                    locks_data["yale"][obj_id] = {}
                if "serial_number" not in locks_data["yale"][obj_id]:
                    locks_data["yale"][obj_id]["serial_number"] = serial
```

## Proto Files Required

Ensure these proto files exist in your integration:

- `proto/weave/trait/description.proto` (DeviceIdentityTrait)
- `proto/weave/trait/power.proto` (BatteryPowerSourceTrait, PowerSourceTrait)

These should already exist in your `yalenestlocktest` project. Copy them to the Home Assistant integration.

## Testing

1. **Test extraction from captures:**
   ```bash
   python extract_all_homekit_data.py --capture-dir captures/[latest]
   ```

2. **Test proto decoding:**
   ```bash
   python decode_homekit_info.py captures/[latest]/*.raw.bin
   ```

3. **Verify in Home Assistant:**
   - Check logs for HomeKit info extraction
   - Verify device attributes include serial_number, battery_level, etc.

## Example Output

After integration, your lock data will include:

```python
{
    "yale": {
        "DEVICE_00177A0000060303": {
            "device_id": "DEVICE_00177A0000060303",
            "serial_number": "00177A0000060303",
            "firmware_version": "1.2.3",
            "manufacturer": "Yale",
            "model": "Linus Lock",
            "battery_level": 85.0,
            "battery_condition": 1,  # NOMINAL
            "battery_status": 1,     # ACTIVE
            "battery_voltage": 3.2,
            "bolt_locked": True,
            "bolt_moving": False,
        }
    },
    "user_id": "USER_...",
    "structure_id": "STRUCTURE_...",
}
```

## Next Steps

1. ✅ Capture messages with DeviceIdentityTrait and BatteryPowerSourceTrait
2. ✅ Extract and verify the data
3. ✅ Update Home Assistant integration to request these traits
4. ✅ Add extraction logic to protobuf_handler
5. ✅ Expose HomeKit attributes in the lock entity
6. ✅ Test with real device

