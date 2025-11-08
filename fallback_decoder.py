"""
Fallback Protobuf Decoder using blackboxprotobuf

This module provides a fallback decoder that uses blackboxprotobuf when
structured proto decoding fails. It can extract additional information
that might not be available in the structured proto definitions.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, Optional

try:
    import blackboxprotobuf as bbp
    BLACKBOX_AVAILABLE = True
except ImportError:
    BLACKBOX_AVAILABLE = False
    logging.warning("blackboxprotobuf not available; fallback decoding disabled")

_LOGGER = logging.getLogger(__name__)


class FallbackDecoder:
    """Fallback decoder using blackboxprotobuf for messages that fail structured decoding."""
    
    def __init__(self, enabled: bool = True):
        self.enabled = enabled and BLACKBOX_AVAILABLE
        if not BLACKBOX_AVAILABLE and enabled:
            _LOGGER.warning("blackboxprotobuf not available; fallback decoding disabled")
    
    def decode(self, raw_data: bytes) -> Optional[Dict[str, Any]]:
        """Decode protobuf message using blackboxprotobuf."""
        if not self.enabled:
            return None
        
        try:
            message_json, typedef = bbp.protobuf_to_json(raw_data)
            if isinstance(message_json, str):
                message_data = json.loads(message_json)
            else:
                message_data = message_json
            
            return {
                "message": message_data,
                "typedef": typedef,
            }
        except Exception as e:
            _LOGGER.debug("Blackbox decode failed: %s", e)
            return None
    
    def extract_device_info(self, decoded_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract device, structure, and user information from blackbox decoded data."""
        info = {
            "devices": [],
            "structures": [],
            "users": [],
            "traits": {},
        }
        
        message_data = decoded_data.get("message", {})
        if not isinstance(message_data, dict):
            return info
        
        def traverse(obj: Any, path: str = "", depth: int = 0):
            if depth > 10:  # Prevent infinite recursion
                return
            
            if isinstance(obj, dict):
                # Look for device/resource IDs (field "1" often contains IDs)
                if "1" in obj and isinstance(obj["1"], str):
                    resource_id = obj["1"]
                    resource_type = obj.get("2", "")
                    
                    # Extract traits (field "4" often contains trait information)
                    traits = []
                    if "4" in obj:
                        trait_list = obj["4"] if isinstance(obj["4"], list) else [obj["4"]]
                        for trait in trait_list:
                            if isinstance(trait, dict):
                                trait_name = trait.get("1", "")
                                trait_type = trait.get("2", "")
                                if trait_type:
                                    traits.append(trait_type)
                    
                    # Categorize by resource type
                    if "yale" in resource_type.lower() or "linus" in resource_type.lower() or "lock" in resource_type.lower():
                        info["devices"].append({
                            "id": resource_id,
                            "type": resource_type,
                            "traits": traits,
                            "path": path,
                        })
                    elif "structure" in resource_type.lower():
                        info["structures"].append({
                            "id": resource_id,
                            "type": resource_type,
                            "path": path,
                        })
                    elif "user" in resource_type.lower():
                        info["users"].append({
                            "id": resource_id,
                            "type": resource_type,
                            "path": path,
                        })
                
                # Recursively traverse
                for key, value in obj.items():
                    traverse(value, f"{path}.{key}" if path else key, depth + 1)
            
            elif isinstance(obj, list):
                for idx, item in enumerate(obj):
                    traverse(item, f"{path}[{idx}]" if path else f"[{idx}]", depth + 1)
        
        traverse(message_data)
        return info
    
    def extract_structure_id(self, decoded_data: Dict[str, Any]) -> Optional[str]:
        """Extract structure ID from blackbox decoded data."""
        device_info = self.extract_device_info(decoded_data)
        structures = device_info.get("structures", [])
        if structures:
            # Try to extract from structure ID format
            structure_id = structures[0]["id"]
            if structure_id.startswith("STRUCTURE_"):
                return structure_id.replace("STRUCTURE_", "")
            return structure_id
        return None
    
    def extract_user_id(self, decoded_data: Dict[str, Any]) -> Optional[str]:
        """Extract user ID from blackbox decoded data."""
        device_info = self.extract_device_info(decoded_data)
        users = device_info.get("users", [])
        if users:
            user_id = users[0]["id"]
            if user_id.startswith("USER_"):
                return user_id.replace("USER_", "")
            return user_id
        return None
    
    def extract_lock_data(self, decoded_data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Extract lock data from blackbox decoded data."""
        locks = {}
        device_info = self.extract_device_info(decoded_data)
        
        for device in device_info.get("devices", []):
            device_id = device["id"]
            if device_id not in locks:
                locks[device_id] = {
                    "device_id": device_id,
                    "traits": device.get("traits", []),
                }
        
        return locks


def create_fallback_handler():
    """Create a fallback decoder instance."""
    return FallbackDecoder(enabled=True)

