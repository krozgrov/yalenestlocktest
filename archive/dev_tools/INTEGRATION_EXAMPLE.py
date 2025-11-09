"""
Example: How to integrate ID extraction into ha-nest-yale-integration

This shows how to modify your protobuf_handler.py to extract structure
and user IDs from messages, even when structured decoding fails.
"""

# ============================================================================
# OPTION 1: Add fallback extraction directly in _process_message
# ============================================================================

# In your protobuf_handler.py, modify the _process_message method:

async def _process_message(self, message):
    """Process a protobuf message with fallback ID extraction."""
    locks_data = {"yale": {}, "user_id": None, "structure_id": None}
    
    try:
        # Try your existing structured decoding
        self.stream_body.Clear()
        self.stream_body.ParseFromString(message)
        
        # Your existing extraction logic...
        for msg in self.stream_body.message:
            for get_op in msg.get:
                # ... existing code ...
                pass
        
    except DecodeError as e:
        _LOGGER.debug("Structured decode failed, trying fallback extraction: %s", e)
        
        # Fallback: Try to extract IDs from the raw message structure
        # Even if full decoding fails, we can still extract IDs
        try:
            # Try a minimal parse to get object IDs
            self.stream_body.Clear()
            # Parse just enough to get object IDs
            partial_parse = self.stream_body.ParseFromString(message[:min(len(message), 2000)])
            
            for msg in self.stream_body.message:
                for get_op in msg.get:
                    obj_id = get_op.object.id if get_op.object.id else None
                    
                    # Extract structure ID
                    if obj_id and obj_id.startswith("STRUCTURE_"):
                        structure_id = obj_id.replace("STRUCTURE_", "")
                        locks_data["structure_id"] = structure_id
                        _LOGGER.debug("Extracted structure_id from object ID: %s", structure_id)
                    
                    # Extract user ID
                    if obj_id and obj_id.startswith("USER_"):
                        user_id = obj_id.replace("USER_", "")
                        locks_data["user_id"] = user_id
                        _LOGGER.debug("Extracted user_id from object ID: %s", user_id)
        except Exception:
            pass  # If even partial parse fails, continue
    
    return locks_data


# ============================================================================
# OPTION 2: Use the fallback_decoder module
# ============================================================================

# First, copy fallback_decoder.py to your integration:
# cp yalenestlocktest/fallback_decoder.py ha-nest-yale-integration/custom_components/nest_yale_lock/

# Then in protobuf_handler.py:

from .fallback_decoder import FallbackDecoder

class NestProtobufHandler:
    def __init__(self):
        # ... existing code ...
        self.fallback_decoder = FallbackDecoder()
    
    async def _process_message(self, message):
        locks_data = {"yale": {}, "user_id": None, "structure_id": None}
        
        try:
            # Try structured decoding first
            locks_data = await self._structured_decode(message)
        except DecodeError:
            # Fallback to blackbox decoding
            _LOGGER.debug("Structured decode failed, using fallback decoder")
            fallback_result = self.fallback_decoder.decode(message)
            
            if fallback_result:
                # Extract missing IDs
                if not locks_data.get("structure_id"):
                    structure_id = self.fallback_decoder.extract_structure_id(fallback_result)
                    if structure_id:
                        locks_data["structure_id"] = structure_id
                        _LOGGER.info("Extracted structure_id via fallback: %s", structure_id)
                
                if not locks_data.get("user_id"):
                    user_id = self.fallback_decoder.extract_user_id(fallback_result)
                    if user_id:
                        locks_data["user_id"] = user_id
                        _LOGGER.info("Extracted user_id via fallback: %s", user_id)
        
        return locks_data


# ============================================================================
# OPTION 3: Improve StructureInfoTrait extraction
# ============================================================================

# In your existing _process_message, improve the StructureInfoTrait handling:

elif "StructureInfoTrait" in (type_url or "") and obj_id:
    try:
        if not property_any:
            _LOGGER.warning("No StructureInfo payload for %s", obj_id)
            continue
        
        structure = nest_structure_pb2.StructureInfoTrait()
        unpacked = property_any.Unpack(structure)
        if not unpacked:
            _LOGGER.warning("Unpacking StructureInfoTrait failed for %s, skipping", obj_id)
            continue
        
        # Try multiple ways to get structure ID
        if structure.legacy_id:
            # Format is usually "structure.XXXXX" or just the ID
            legacy_id = structure.legacy_id
            if "." in legacy_id:
                locks_data["structure_id"] = legacy_id.split(".")[1]
            else:
                locks_data["structure_id"] = legacy_id
            _LOGGER.debug("Extracted structure_id from legacy_id: %s", locks_data["structure_id"])
        
        # Also check if obj_id itself is a structure ID
        elif obj_id.startswith("STRUCTURE_"):
            locks_data["structure_id"] = obj_id.replace("STRUCTURE_", "")
            _LOGGER.debug("Extracted structure_id from obj_id: %s", locks_data["structure_id"])
        
        # Fallback: use obj_id if it looks like a structure ID
        elif obj_id and len(obj_id) == 16 and all(c in '0123456789ABCDEF' for c in obj_id):
            locks_data["structure_id"] = obj_id
            _LOGGER.debug("Extracted structure_id from obj_id (format match): %s", locks_data["structure_id"])
        
    except Exception as err:
        _LOGGER.error("Failed to parse StructureInfoTrait for %s: %s", obj_id, err, exc_info=True)


# ============================================================================
# Using the IDs in API calls
# ============================================================================

# In your api_client.py or wherever you send commands:

# When sending lock/unlock commands:
if structure_id:
    headers["X-Nest-Structure-Id"] = structure_id
    _LOGGER.debug("Including structure_id in request: %s", structure_id)

# When building the command request:
if user_id:
    request.boltLockActor.originator.resourceId = user_id
    _LOGGER.debug("Setting user_id in request: %s", user_id)

