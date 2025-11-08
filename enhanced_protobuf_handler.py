"""
Enhanced protobuf handler that extracts ALL trait data for testing.

This extends the base handler to decode all traits, not just lock-specific ones.
"""

import logging
import asyncio
from google.protobuf.message import DecodeError
from google.protobuf.any_pb2 import Any

from protobuf_handler import NestProtobufHandler
from proto.weave.trait import security_pb2 as weave_security_pb2
from proto.nest.trait import structure_pb2 as nest_structure_pb2
from proto.nest import rpc_pb2 as rpc_pb2

# Import HomeKit trait decoders
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "proto"))

try:
    from proto.weave.trait import description_pb2
    from proto.weave.trait import power_pb2
    PROTO_AVAILABLE = True
except ImportError:
    PROTO_AVAILABLE = False

_LOGGER = logging.getLogger(__name__)


def _normalize_any_type(any_message: Any) -> Any:
    """Map legacy Nest type URLs onto googleapis prefix."""
    if not isinstance(any_message, Any):
        return any_message
    type_url = any_message.type_url or ""
    if type_url.startswith("type.nestlabs.com/"):
        normalized = Any()
        normalized.value = any_message.value
        normalized.type_url = type_url.replace("type.nestlabs.com/", "type.googleapis.com/", 1)
        return normalized
    return any_message


class EnhancedProtobufHandler(NestProtobufHandler):
    """Enhanced handler that extracts all trait data."""
    
    async def _process_message(self, message):
        """Process message and extract all trait data."""
        # Call parent to get lock data
        locks_data = await super()._process_message(message)
        
        # Also extract all trait data
        all_traits = {}
        
        try:
            stream_body = self.stream_body
            
            for msg in stream_body.message:
                for get_op in msg.get:
                    obj_id = get_op.object.id if get_op.object.id else None
                    obj_key = get_op.object.key if get_op.object.key else "unknown"
                    
                    property_any = getattr(get_op.data, "property", None)
                    property_any = _normalize_any_type(property_any) if property_any else None
                    type_url = getattr(property_any, "type_url", None) if property_any else None
                    
                    if not type_url and 7 in get_op:
                        type_url = "weave.trait.security.BoltLockTrait"
                    
                    if not type_url or not property_any:
                        continue
                    
                    trait_key = f"{obj_id}:{type_url}"
                    trait_data = {"object_id": obj_id, "type_url": type_url, "decoded": False}
                    
                    # Try to decode each trait type
                    try:
                        # DeviceIdentityTrait
                        if "DeviceIdentityTrait" in type_url and PROTO_AVAILABLE:
                            trait = description_pb2.DeviceIdentityTrait()
                            property_any.Unpack(trait)
                            trait_data["decoded"] = True
                            trait_data["data"] = {
                                "serial_number": trait.serial_number if trait.serial_number else None,
                                "firmware_version": trait.fw_version if trait.fw_version else None,
                                "manufacturer": trait.manufacturer.value if trait.HasField("manufacturer") else None,
                                "model": trait.model_name.value if trait.HasField("model_name") else None,
                            }
                        
                        # BatteryPowerSourceTrait
                        elif "BatteryPowerSourceTrait" in type_url and PROTO_AVAILABLE:
                            trait = power_pb2.BatteryPowerSourceTrait()
                            property_any.Unpack(trait)
                            trait_data["decoded"] = True
                            trait_data["data"] = {
                                "battery_level": trait.remaining.remainingPercent.value if trait.HasField("remaining") and trait.remaining.HasField("remainingPercent") else None,
                                "voltage": trait.assessedVoltage.value if trait.HasField("assessedVoltage") else None,
                                "condition": trait.condition,
                                "status": trait.status,
                                "replacement_indicator": trait.replacementIndicator,
                            }
                        
                        # Other traits are already handled by parent
                    
                    except Exception as e:
                        trait_data["error"] = str(e)
                    
                    all_traits[trait_key] = trait_data
        
        except Exception as e:
            _LOGGER.debug(f"Error extracting traits: {e}")
        
        # Add all traits to locks_data
        locks_data["all_traits"] = all_traits
        
        return locks_data

