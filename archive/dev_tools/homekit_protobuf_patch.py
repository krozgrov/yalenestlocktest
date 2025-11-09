#!/usr/bin/env python3
"""
Example code to add HomeKit information extraction to protobuf_handler.py

This shows the exact code changes needed to extract:
- Serial numbers
- Battery information
- Firmware versions
- Model/manufacturer info
"""

# ============================================================================
# ADD TO protobuf_handler.py imports section:
# ============================================================================

# Add these imports at the top with other proto imports:
"""
from .proto.weave.trait import description_pb2 as weave_description_pb2
from .proto.weave.trait import power_pb2 as weave_power_pb2
"""

# ============================================================================
# ADD NEW METHOD to NestProtobufHandler class:
# ============================================================================

def _extract_homekit_info(self, get_op, property_any, obj_id):
    """
    Extract HomeKit-relevant information from protobuf traits.
    
    Returns dict with:
    - serial_number: Device serial number
    - firmware_version: Firmware version string
    - manufacturer: Device manufacturer
    - model: Device model name
    - battery_level: Battery percentage (0-100)
    - battery_condition: Battery condition (0=UNSPECIFIED, 1=NOMINAL, 2=CRITICAL)
    - battery_status: Battery status (0=UNSPECIFIED, 1=ACTIVE, 2=STANDBY, 3=INACTIVE)
    - battery_voltage: Battery voltage
    - battery_replacement_indicator: Replacement needed (0=UNSPECIFIED, 1=NOT_AT_ALL, 2=SOON, 3=IMMEDIATELY)
    """
    if not property_any:
        return {}
    
    homekit_info = {}
    type_url = getattr(property_any, "type_url", None) if property_any else None
    
    # DeviceIdentityTrait - Serial, firmware, model, manufacturer
    if "DeviceIdentityTrait" in (type_url or ""):
        try:
            identity = weave_description_pb2.DeviceIdentityTrait()
            property_any = _normalize_any_type(property_any)
            unpacked = property_any.Unpack(identity)
            if unpacked:
                if identity.serial_number:
                    homekit_info["serial_number"] = identity.serial_number
                if identity.fw_version:
                    homekit_info["firmware_version"] = identity.fw_version
                if identity.HasField("manufacturer"):
                    homekit_info["manufacturer"] = identity.manufacturer.value
                if identity.HasField("model_name"):
                    homekit_info["model"] = identity.model_name.value
                _LOGGER.debug("Extracted DeviceIdentityTrait for %s: %s", obj_id, homekit_info)
        except Exception as e:
            _LOGGER.debug("Failed to extract DeviceIdentityTrait for %s: %s", obj_id, e)
    
    # BatteryPowerSourceTrait - Battery level, status, condition
    elif "BatteryPowerSourceTrait" in (type_url or ""):
        try:
            battery = weave_power_pb2.BatteryPowerSourceTrait()
            property_any = _normalize_any_type(property_any)
            unpacked = property_any.Unpack(battery)
            if unpacked:
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
                _LOGGER.debug("Extracted BatteryPowerSourceTrait for %s: %s", obj_id, homekit_info)
        except Exception as e:
            _LOGGER.debug("Failed to extract BatteryPowerSourceTrait for %s: %s", obj_id, e)
    
    # PowerSourceTrait - Alternative power source info
    elif "PowerSourceTrait" in (type_url or "") and "BatteryPowerSourceTrait" not in (type_url or ""):
        try:
            power = weave_power_pb2.PowerSourceTrait()
            property_any = _normalize_any_type(property_any)
            unpacked = property_any.Unpack(power)
            if unpacked:
                if power.HasField("assessedVoltage"):
                    homekit_info["battery_voltage"] = power.assessedVoltage.value
                if power.condition:
                    homekit_info["battery_condition"] = power.condition
                if power.status:
                    homekit_info["battery_status"] = power.status
                homekit_info["power_present"] = power.present
                _LOGGER.debug("Extracted PowerSourceTrait for %s: %s", obj_id, homekit_info)
        except Exception as e:
            _LOGGER.debug("Failed to extract PowerSourceTrait for %s: %s", obj_id, e)
    
    return homekit_info


# ============================================================================
# MODIFY _process_message method - Add HomeKit extraction:
# ============================================================================

# In the _process_message method, after processing each trait, add:

"""
                    # Extract HomeKit information from any trait
                    if property_any:
                        homekit_info = self._extract_homekit_info(get_op, property_any, obj_id)
                        if homekit_info and obj_id:
                            # Initialize device entry if it doesn't exist
                            if obj_id not in locks_data["yale"]:
                                locks_data["yale"][obj_id] = {}
                            # Merge HomeKit info into device data
                            locks_data["yale"][obj_id].update(homekit_info)
                    
                    # Extract serial number from device ID if not already found
                    if obj_id and obj_id.startswith("DEVICE_"):
                        serial = obj_id.replace("DEVICE_", "")
                        if obj_id not in locks_data["yale"]:
                            locks_data["yale"][obj_id] = {}
                        if "serial_number" not in locks_data["yale"][obj_id]:
                            locks_data["yale"][obj_id]["serial_number"] = serial
                            _LOGGER.debug("Extracted serial number from device ID: %s", serial)
"""

# ============================================================================
# MODIFY api_client.py - Add HomeKit traits to observe payload:
# ============================================================================

# In the _build_observe_payload method, add these traits:

"""
    trait_names = [
        # Existing traits
        "nest.trait.user.UserInfoTrait",
        "nest.trait.structure.StructureInfoTrait",
        "weave.trait.security.BoltLockTrait",
        "weave.trait.security.BoltLockSettingsTrait",
        "weave.trait.security.BoltLockCapabilitiesTrait",
        "weave.trait.security.PincodeInputTrait",
        "weave.trait.security.TamperTrait",
        # HomeKit-relevant traits
        "weave.trait.description.DeviceIdentityTrait",  # Serial, firmware, model
        "weave.trait.power.BatteryPowerSourceTrait",    # Battery level, status
    ]
"""

# ============================================================================
# Example usage in lock.py:
# ============================================================================

# You can then access HomeKit info in the lock entity:

"""
@property
def device_info(self):
    '''Return device information for HomeKit.'''
    info = {
        "identifiers": {(DOMAIN, self.device_id)},
        "name": self.name,
        "manufacturer": "Yale",
        "model": "Linus Lock",
    }
    
    # Add serial number if available
    if hasattr(self, "_homekit_info") and self._homekit_info.get("serial_number"):
        info["serial_number"] = self._homekit_info["serial_number"]
    
    # Add firmware version if available
    if hasattr(self, "_homekit_info") and self._homekit_info.get("firmware_version"):
        info["sw_version"] = self._homekit_info["firmware_version"]
    
    return info

@property
def battery_level(self):
    '''Return battery level if available.'''
    if hasattr(self, "_homekit_info") and self._homekit_info.get("battery_level") is not None:
        return int(self._homekit_info["battery_level"])
    return None
"""

