"""
Enhanced protobuf handler that extracts ALL trait data.

This is a copy of protobuf_handler.py with enhancements to decode all traits.
"""

import os
import logging
import asyncio
from google.protobuf.message import DecodeError
from google.protobuf.any_pb2 import Any
from proto.weave.trait import security_pb2 as weave_security_pb2
from proto.nest.trait import user_pb2 as nest_user_pb2
from proto.nest.trait import structure_pb2 as nest_structure_pb2
from proto.nest import rpc_pb2 as rpc
from protobuf_manager import read_protobuf_file
from const import (
    USER_AGENT_STRING,
    URL_PROTOBUF,
    ENDPOINT_OBSERVE,
    PRODUCTION_HOSTNAME,
)

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

MAX_BUFFER_SIZE = 4194304  # 4MB
LOG_PAYLOAD_TO_FILE = True
RETRY_DELAY_SECONDS = 10
STREAM_TIMEOUT_SECONDS = 600  # 10min
PING_INTERVAL_SECONDS = 60
CATALOG_THRESHOLD = 20000  # 20KB

def _normalize_any_type(any_message: Any) -> Any:
    """Map non-standard type URLs (e.g. type.nestlabs.com) to the canonical googleapis prefix."""
    if not isinstance(any_message, Any):
        return any_message
    type_url = any_message.type_url or ""
    if type_url.startswith("type.nestlabs.com/"):
        normalized = Any()
        normalized.value = any_message.value
        normalized.type_url = type_url.replace("type.nestlabs.com/", "type.googleapis.com/", 1)
        return normalized
    return any_message

class EnhancedProtobufHandler:
    def __init__(self):
        self.buffer = bytearray()
        self.pending_length = None
        self.stream_body = rpc.StreamBody()

    def _decode_varint(self, buffer, pos):
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
                _LOGGER.debug(f"Decoded varint: {value} from position {start} using {pos - start} bytes")
                return value, pos
            if pos - start >= max_bytes:
                _LOGGER.error(f"Varint too long at pos {start}")
                return None, pos
        _LOGGER.error(f"Incomplete varint at pos {start}")
        return None, pos

    async def _process_message(self, message):
        _LOGGER.debug(f"Raw chunk (length={len(message)}): {message.hex()}")

        if not message:
            _LOGGER.error("Empty protobuf message received.")
            return {"yale": {}, "user_id": None, "structure_id": None, "all_traits": {}}

        locks_data = {"yale": {}, "user_id": None, "structure_id": None, "all_traits": {}}
        all_traits = {}

        try:
            self.stream_body.Clear()
            self.stream_body.ParseFromString(message)
            _LOGGER.debug(f"Parsed StreamBody: {self.stream_body}")

            for msg in self.stream_body.message:
                for get_op in msg.get:
                    obj_id = get_op.object.id if get_op.object.id else None
                    obj_key = get_op.object.key if get_op.object.key else "unknown"

                    property_any = getattr(get_op.data, "property", None)
                    property_any = _normalize_any_type(property_any) if property_any else None
                    type_url = getattr(property_any, "type_url", None) if property_any else None
                    if not type_url and 7 in get_op:
                        type_url = "weave.trait.security.BoltLockTrait"

                    _LOGGER.debug(f"Extracting `{type_url}` for `{obj_id}` with key `{obj_key}`")

                    # Extract trait data for ALL traits
                    if property_any and type_url:
                        trait_key = f"{obj_id}:{type_url}" if obj_id and type_url else None
                        trait_info = {"object_id": obj_id, "type_url": type_url, "decoded": False}
                        
                        try:
                            # DeviceIdentityTrait
                            if "DeviceIdentityTrait" in type_url and PROTO_AVAILABLE:
                                trait = description_pb2.DeviceIdentityTrait()
                                property_any.Unpack(trait)
                                trait_info["decoded"] = True
                                trait_info["data"] = {
                                    "serial_number": trait.serial_number if trait.serial_number else None,
                                    "firmware_version": trait.fw_version if trait.fw_version else None,
                                    "manufacturer": trait.manufacturer.value if trait.HasField("manufacturer") else None,
                                    "model": trait.model_name.value if trait.HasField("model_name") else None,
                                }
                                _LOGGER.info(f"✅ Decoded DeviceIdentityTrait for {obj_id}: serial={trait_info['data'].get('serial_number')}, fw={trait_info['data'].get('firmware_version')}")
                            
                            # BatteryPowerSourceTrait
                            elif "BatteryPowerSourceTrait" in type_url and PROTO_AVAILABLE:
                                trait = power_pb2.BatteryPowerSourceTrait()
                                property_any.Unpack(trait)
                                trait_info["decoded"] = True
                                trait_info["data"] = {
                                    "battery_level": trait.remaining.remainingPercent.value if trait.HasField("remaining") and trait.remaining.HasField("remainingPercent") else None,
                                    "voltage": trait.assessedVoltage.value if trait.HasField("assessedVoltage") else None,
                                    "condition": trait.condition,
                                    "status": trait.status,
                                    "replacement_indicator": trait.replacementIndicator,
                                }
                                _LOGGER.info(f"✅ Decoded BatteryPowerSourceTrait for {obj_id}: level={trait_info['data'].get('battery_level')}, voltage={trait_info['data'].get('voltage')}")
                        except Exception as e:
                            trait_info["error"] = str(e)
                            _LOGGER.debug(f"Error decoding trait {type_url}: {e}")
                        
                        # Store trait info
                        if trait_key:
                            all_traits[trait_key] = trait_info

                    # Existing lock-specific processing
                    if "BoltLockTrait" in (type_url or "") and obj_id:
                        bolt_lock = weave_security_pb2.BoltLockTrait()
                        try:
                            if not property_any:
                                _LOGGER.warning(f"No property payload for {obj_id}, skipping BoltLockTrait decode")
                                continue
                            unpacked = property_any.Unpack(bolt_lock)
                            if not unpacked:
                                _LOGGER.warning(f"Unpacking failed for {obj_id}, skipping")
                                continue

                            locks_data["yale"][obj_id] = {
                                "device_id": obj_id,
                                "bolt_locked": bolt_lock.lockedState == weave_security_pb2.BoltLockTrait.BOLT_LOCKED_STATE_LOCKED,
                                "bolt_moving": bolt_lock.actuatorState not in [weave_security_pb2.BoltLockTrait.BOLT_ACTUATOR_STATE_OK],
                                "actuator_state": bolt_lock.actuatorState
                            }
                            if bolt_lock.boltLockActor.originator.resourceId:
                                locks_data["user_id"] = bolt_lock.boltLockActor.originator.resourceId
                            _LOGGER.debug(f"Parsed BoltLockTrait for {obj_id}: {locks_data['yale'][obj_id]}, user_id={locks_data['user_id']}")

                        except DecodeError as e:
                            _LOGGER.error(f"Failed to decode BoltLockTrait for {obj_id}: {e}")
                            continue
                        except Exception as e:
                            _LOGGER.error(f"Unexpected error unpacking BoltLockTrait for {obj_id}: {e}")
                            continue

                    elif "StructureInfoTrait" in (type_url or "") and obj_id:
                        try:
                            _LOGGER.debug(f"Raw structure_info data for {obj_id}: {property_any}")
                            if property_any:
                                structure = nest_structure_pb2.StructureInfoTrait()
                                unpacked = property_any.Unpack(structure)
                                if not unpacked:
                                    _LOGGER.warning(f"Unpacking StructureInfoTrait failed for {obj_id}, skipping")
                                    continue
                                if structure.legacy_id:
                                  locks_data["structure_id"] = structure.legacy_id.split('.')[1]
                                _LOGGER.debug(f"StructureInfoTrait value: {structure}")
                                _LOGGER.debug(f"Parsed structure_info for {obj_id}: structure_id={locks_data['structure_id']}")
                        except Exception as e:
                            _LOGGER.error(f"Failed to parse structure_info for {obj_id}: {e}")
                    elif "UserInfoTrait" in (type_url or ""):
                        try:
                            locks_data["user_id"] = obj_id
                        except Exception as e:
                            _LOGGER.error(f"Failed to parse UserInfoTrait: {e}")

            locks_data["all_traits"] = all_traits
            _LOGGER.debug(f"Final lock data: {locks_data}")
            return locks_data

        except DecodeError as e:
            _LOGGER.error(f"DecodeError in StreamBody: {e}")
            return locks_data
        except Exception as e:
            _LOGGER.error(f"Unexpected error processing message: {e}", exc_info=True)
            return locks_data

    async def stream(self, api_url, headers, observe_data, connection):
        attempt = 0
        while True:
            attempt += 1
            _LOGGER.info(f"Starting stream attempt {attempt} with headers: {headers}")
            self.buffer = bytearray()
            self.pending_length = None
            try:
                async for data in connection.stream(api_url, headers, observe_data):
                    if not isinstance(data, bytes) or not data.strip():
                        continue

                    # Try parsing the chunk directly as StreamBody first (like main.py does)
                    # If that fails, try varint extraction
                    try:
                        test_stream = rpc.StreamBody()
                        test_stream.ParseFromString(data)
                        # Success! This chunk is a complete StreamBody
                        locks_data = await self._process_message(data)
                        if locks_data.get("yale") or locks_data.get("user_id") or locks_data.get("structure_id") or locks_data.get("all_traits"):
                            yield locks_data
                        continue
                    except:
                        # Not a direct StreamBody, try varint extraction
                        pass

                    # Varint extraction path (for gRPC-web format)
                    if self.pending_length is None:
                        self.pending_length, offset = self._decode_varint(data, 0)
                        if self.pending_length is None or offset >= len(data):
                            _LOGGER.warning(f"Invalid varint in chunk: {data.hex()[:200]}... skipping")
                            continue
                        self.buffer.extend(data[offset:])
                    else:
                        self.buffer.extend(data)

                    _LOGGER.debug(f"Buffer size: {len(self.buffer)} bytes, pending_length: {self.pending_length}")

                    while self.pending_length and len(self.buffer) >= self.pending_length:
                        message = self.buffer[:self.pending_length]
                        self.buffer = self.buffer[self.pending_length:]
                        locks_data = await self._process_message(message)
                        self.pending_length = None if len(self.buffer) < 5 else self._decode_varint(self.buffer, 0)[0]

                        if locks_data.get("yale") or locks_data.get("user_id") or locks_data.get("structure_id") or locks_data.get("all_traits"):
                            yield locks_data
                            continue

                    if len(self.buffer) >= CATALOG_THRESHOLD and self.pending_length:
                        message = self.buffer[:self.pending_length]
                        self.buffer = self.buffer[self.pending_length:]
                        locks_data = await self._process_message(message)
                        self.pending_length = None if len(self.buffer) < 5 else self._decode_varint(self.buffer, 0)[0]

                        if locks_data.get("yale") or locks_data.get("user_id") or locks_data.get("structure_id") or locks_data.get("all_traits"):
                            yield locks_data

            except Exception as e:
                _LOGGER.error(f"Stream error: {e}", exc_info=True)
                await asyncio.sleep(RETRY_DELAY_SECONDS)

