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

_LOGGER = logging.getLogger(__name__)
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s")

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

class NestProtobufHandler:
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
            return {"yale": {}, "user_id": None, "structure_id": None}

        locks_data = {"yale": {}, "user_id": None, "structure_id": None, "all_traits": {}}
        all_traits = {}

        # Import HomeKit trait decoders
        try:
            from proto.weave.trait import description_pb2
            from proto.weave.trait import power_pb2
            PROTO_AVAILABLE = True
        except ImportError:
            PROTO_AVAILABLE = False

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
                    
                    # Extract ALL trait data
                    if property_any and type_url:
                        trait_key = f"{obj_id}:{type_url}"
                        trait_info = {"object_id": obj_id, "type_url": type_url, "decoded": False}
                        
                        try:
                            # DeviceIdentityTrait
                            if "DeviceIdentityTrait" in type_url and PROTO_AVAILABLE:
                                trait = description_pb2.DeviceIdentityTrait()
                                property_any.Unpack(trait)
                                trait_info["decoded"] = True
                                
                                # Extract model with detailed logging
                                model_value = None
                                if trait.HasField("model_name"):
                                    model_value = trait.model_name.value
                                    if model_value:
                                        _LOGGER.info(f"✅ Model found in DeviceIdentityTrait: '{model_value}'")
                                    else:
                                        _LOGGER.warning(f"⚠️  model_name field exists but value is empty")
                                else:
                                    _LOGGER.warning(f"⚠️  model_name field not present in DeviceIdentityTrait")
                                
                                # Extract manufacturer with detailed logging
                                manufacturer_value = None
                                if trait.HasField("manufacturer"):
                                    manufacturer_value = trait.manufacturer.value
                                    if manufacturer_value:
                                        _LOGGER.debug(f"Manufacturer found: '{manufacturer_value}'")
                                
                                trait_info["data"] = {
                                    "serial_number": trait.serial_number if trait.serial_number else None,
                                    "firmware_version": trait.fw_version if trait.fw_version else None,
                                    "manufacturer": manufacturer_value,
                                    "model": model_value,
                                }
                                _LOGGER.info(f"✅ Decoded DeviceIdentityTrait for {obj_id}: serial={trait_info['data'].get('serial_number')}, fw={trait_info['data'].get('firmware_version')}, model={trait_info['data'].get('model')}, manufacturer={trait_info['data'].get('manufacturer')}")
                            
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
                            
                            # BoltLockTrait (main trait - extract ALL fields)
                            elif "BoltLockTrait" in type_url and "BoltLockSettings" not in type_url and "BoltLockCapabilities" not in type_url and PROTO_AVAILABLE:
                                trait = weave_security_pb2.BoltLockTrait()
                                property_any.Unpack(trait)
                                trait_info["decoded"] = True
                                
                                # Extract boltLockActor details
                                actor_data = None
                                if trait.HasField("boltLockActor"):
                                    actor = trait.boltLockActor
                                    actor_data = {
                                        "method": actor.method,
                                        "originator": actor.originator.resourceId if actor.HasField("originator") and actor.originator.resourceId else None,
                                        "agent": actor.agent.resourceId if actor.HasField("agent") and actor.agent.resourceId else None,
                                    }
                                
                                # Extract timestamp
                                locked_state_changed_at = None
                                if trait.HasField("lockedStateLastChangedAt"):
                                    ts = trait.lockedStateLastChangedAt
                                    # Convert to seconds since epoch
                                    locked_state_changed_at = ts.seconds + (ts.nanos / 1e9) if ts.seconds else None
                                
                                trait_info["data"] = {
                                    "state": trait.state,
                                    "actuator_state": trait.actuatorState,
                                    "locked_state": trait.lockedState,
                                    "bolt_lock_actor": actor_data,
                                    "locked_state_last_changed_at": locked_state_changed_at,
                                }
                                _LOGGER.info(f"✅ Decoded BoltLockTrait for {obj_id}: state={trait.state}, locked_state={trait.lockedState}, actuator_state={trait.actuatorState}")
                            
                            # BoltLockSettingsTrait
                            elif "BoltLockSettingsTrait" in type_url and PROTO_AVAILABLE:
                                trait = weave_security_pb2.BoltLockSettingsTrait()
                                property_any.Unpack(trait)
                                trait_info["decoded"] = True
                                
                                # Extract autoRelockDuration
                                auto_relock_duration_seconds = None
                                if trait.HasField("autoRelockDuration"):
                                    duration = trait.autoRelockDuration
                                    auto_relock_duration_seconds = duration.seconds + (duration.nanos / 1e9) if duration.seconds else None
                                
                                # For bool fields in proto3, check if field was set (HasField) or use default
                                # autoRelockOn defaults to False in proto3 if not set
                                auto_relock_on = None
                                if trait.HasField("autoRelockOn"):
                                    auto_relock_on = trait.autoRelockOn
                                
                                trait_info["data"] = {
                                    "auto_relock_on": auto_relock_on,
                                    "auto_relock_duration_seconds": auto_relock_duration_seconds,
                                }
                                
                                # Only log if we have at least one field
                                if auto_relock_on is not None or auto_relock_duration_seconds is not None:
                                    _LOGGER.info(f"✅ Decoded BoltLockSettingsTrait for {obj_id}: auto_relock_on={auto_relock_on}, duration={auto_relock_duration_seconds}")
                                else:
                                    _LOGGER.debug(f"✅ Decoded BoltLockSettingsTrait for {obj_id} but no fields present in message")
                            
                            # BoltLockCapabilitiesTrait
                            elif "BoltLockCapabilitiesTrait" in type_url and PROTO_AVAILABLE:
                                trait = weave_security_pb2.BoltLockCapabilitiesTrait()
                                property_any.Unpack(trait)
                                trait_info["decoded"] = True
                                
                                # Extract maxAutoRelockDuration
                                max_auto_relock_duration_seconds = None
                                if trait.HasField("maxAutoRelockDuration"):
                                    duration = trait.maxAutoRelockDuration
                                    max_auto_relock_duration_seconds = duration.seconds + (duration.nanos / 1e9) if duration.seconds else None
                                
                                trait_info["data"] = {
                                    "handedness": trait.handedness,
                                    "max_auto_relock_duration_seconds": max_auto_relock_duration_seconds,
                                }
                                _LOGGER.info(f"✅ Decoded BoltLockCapabilitiesTrait for {obj_id}: handedness={trait.handedness}, max_duration={max_auto_relock_duration_seconds}")
                            
                            # PincodeInputTrait
                            elif "PincodeInputTrait" in type_url and PROTO_AVAILABLE:
                                trait = weave_security_pb2.PincodeInputTrait()
                                property_any.Unpack(trait)
                                trait_info["decoded"] = True
                                trait_info["data"] = {
                                    "pincode_input_state": trait.pincodeInputState,
                                }
                                _LOGGER.debug(f"✅ Decoded PincodeInputTrait for {obj_id}: state={trait.pincodeInputState}")
                            
                            # TamperTrait
                            elif "TamperTrait" in type_url and PROTO_AVAILABLE:
                                trait = weave_security_pb2.TamperTrait()
                                property_any.Unpack(trait)
                                trait_info["decoded"] = True
                                
                                # Extract timestamps
                                first_observed_at = None
                                first_observed_at_ms = None
                                if trait.HasField("firstObservedAt"):
                                    ts = trait.firstObservedAt
                                    first_observed_at = ts.seconds + (ts.nanos / 1e9) if ts.seconds else None
                                if trait.HasField("firstObservedAtMs"):
                                    ts = trait.firstObservedAtMs
                                    first_observed_at_ms = ts.seconds + (ts.nanos / 1e9) if ts.seconds else None
                                
                                trait_info["data"] = {
                                    "tamper_state": trait.tamperState,
                                    "first_observed_at": first_observed_at,
                                    "first_observed_at_ms": first_observed_at_ms,
                                }
                                _LOGGER.debug(f"✅ Decoded TamperTrait for {obj_id}: tamper_state={trait.tamperState}")
                        except Exception as e:
                            trait_info["error"] = str(e)
                            _LOGGER.debug(f"Error decoding trait {type_url}: {e}")
                        
                        all_traits[trait_key] = trait_info

                    # Existing lock-specific processing (keep for backward compatibility)
                    # Note: Full trait data is already stored in all_traits above
                    if "BoltLockTrait" in (type_url or "") and "BoltLockSettings" not in type_url and "BoltLockCapabilities" not in type_url and obj_id:
                        bolt_lock = weave_security_pb2.BoltLockTrait()
                        try:
                            if not property_any:
                                _LOGGER.warning(f"No property payload for {obj_id}, skipping BoltLockTrait decode")
                                continue
                            unpacked = property_any.Unpack(bolt_lock)
                            if not unpacked:
                                _LOGGER.warning(f"Unpacking failed for {obj_id}, skipping")
                                continue

                            # Extract basic lock state for backward compatibility
                            locks_data["yale"][obj_id] = {
                                "device_id": obj_id,
                                "bolt_locked": bolt_lock.lockedState == weave_security_pb2.BoltLockTrait.BOLT_LOCKED_STATE_LOCKED,
                                "bolt_moving": bolt_lock.actuatorState not in [weave_security_pb2.BoltLockTrait.BOLT_ACTUATOR_STATE_OK],
                                "actuator_state": bolt_lock.actuatorState,
                                # Add additional fields
                                "state": bolt_lock.state,
                                "locked_state": bolt_lock.lockedState,
                            }
                            
                            # Extract actor info
                            if bolt_lock.HasField("boltLockActor"):
                                actor = bolt_lock.boltLockActor
                                locks_data["yale"][obj_id]["actor_method"] = actor.method
                                if actor.HasField("originator") and actor.originator.resourceId:
                                    locks_data["yale"][obj_id]["actor_originator"] = actor.originator.resourceId
                                    locks_data["user_id"] = actor.originator.resourceId
                                if actor.HasField("agent") and actor.agent.resourceId:
                                    locks_data["yale"][obj_id]["actor_agent"] = actor.agent.resourceId
                            
                            # Extract timestamp
                            if bolt_lock.HasField("lockedStateLastChangedAt"):
                                ts = bolt_lock.lockedStateLastChangedAt
                                locked_state_changed_at = ts.seconds + (ts.nanos / 1e9) if ts.seconds else None
                                if locked_state_changed_at:
                                    locks_data["yale"][obj_id]["locked_state_last_changed_at"] = locked_state_changed_at
                            
                            _LOGGER.debug(f"Parsed BoltLockTrait for {obj_id}: {locks_data['yale'][obj_id]}, user_id={locks_data.get('user_id')}")

                        except DecodeError as e:
                            _LOGGER.error(f"Failed to decode BoltLockTrait for {obj_id}: {e}")
                            continue
                        except Exception as e:
                            _LOGGER.error(f"Unexpected error unpacking BoltLockTrait for {obj_id}: {e}")
                            continue

                    elif "StructureInfoTrait" in type_url and obj_id:
                        try:
                            # Log raw structure_info for debugging
                            _LOGGER.debug(f"Raw structure_info data for {obj_id}: {property_any}")
                            # Extract legacyId or use obj_id as fallback
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
                    elif "UserInfoTrait" in type_url:
                        try:
                            locks_data["user_id"] = obj_id
                        except Exception as e:
                            _LOGGER.error(f"Failed to parse UserInfoTrait: {e}")

            locks_data["all_traits"] = all_traits
            _LOGGER.debug(f"Final lock data: {locks_data}")
            if all_traits:
                _LOGGER.info(f"Decoded {len([t for t in all_traits.values() if t.get('decoded')])} trait(s) successfully")
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
                    if not isinstance(data, bytes):
                        _LOGGER.error(f"Received non-bytes data: {data}")
                        continue

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

                        if locks_data.get("yale"):
                            yield locks_data
                            continue

                    if len(self.buffer) >= CATALOG_THRESHOLD and self.pending_length:
                        message = self.buffer[:self.pending_length]
                        self.buffer = self.buffer[self.pending_length:]
                        locks_data = await self._process_message(message)
                        self.pending_length = None if len(self.buffer) < 5 else self._decode_varint(self.buffer, 0)[0]

                        if locks_data.get("yale"):
                            yield locks_data
                            continue

                await asyncio.sleep(PING_INTERVAL_SECONDS / 1000)

            except asyncio.TimeoutError:
                _LOGGER.warning("Stream timeout, retrying...")
                yield {"yale": {}, "user_id": None, "structure_id": None}
            except Exception as e:
                _LOGGER.error(f"Stream error: {e}", exc_info=True)

            _LOGGER.info(f"Retrying stream in {RETRY_DELAY_SECONDS} seconds")
            await asyncio.sleep(RETRY_DELAY_SECONDS)
            yield None

    async def refresh_state(self, connection, access_token):
        headers = {
            "Authorization": f"Basic {access_token}",
            "Content-Type": "application/x-protobuf",
            "User-Agent": USER_AGENT_STRING,
            "X-Accept-Response-Streaming": "true",
            "Accept": "application/x-protobuf",
        }

        api_url = f"{URL_PROTOBUF.format(grpc_hostname=PRODUCTION_HOSTNAME['grpc_hostname'])}{ENDPOINT_OBSERVE}"
        observe_data = await read_protobuf_file(os.path.join(os.path.dirname(__file__), "proto", "ObserveTraits.bin"))

        try:
            async with connection.session.post(api_url, headers=headers, data=observe_data) as response:
                if response.status != 200:
                    _LOGGER.error(f"HTTP {response.status}: {await response.text()}")
                    return {}
                async for chunk in response.content.iter_chunked(1024):
                    locks_data = await self._process_message(chunk)
                    if locks_data.get("yale"):
                        return locks_data
        except Exception as e:
            _LOGGER.error(f"Refresh state error: {e}", exc_info=True)
        return {"yale": {}, "user_id": None, "structure_id": None}
