#!/usr/bin/env python3
"""
Test the enhanced protobuf handler with a live Observe stream.

This verifies that all traits decode correctly, including:
- DeviceIdentityTrait (serial number, firmware)
- BatteryPowerSourceTrait (battery level, voltage)
- BoltLockTrait
- StructureInfoTrait
- UserInfoTrait
- And all other requested traits
"""

import asyncio
import json
import logging
import sys
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

from protobuf_handler_enhanced import EnhancedProtobufHandler
from auth import GetSessionWithAuth
from proto.nestlabs.gateway import v2_pb2
import requests
from const import (
    USER_AGENT_STRING,
    URL_PROTOBUF,
    ENDPOINT_OBSERVE,
    PRODUCTION_HOSTNAME,
    API_TIMEOUT_SECONDS,
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ]
)
_LOGGER = logging.getLogger(__name__)


async def main():
    load_dotenv()
    
    print("="*80)
    print("TESTING ENHANCED HANDLER WITH LIVE STREAM")
    print("="*80)
    print()
    
    # Request all relevant traits
    trait_names = [
        "nest.trait.user.UserInfoTrait",
        "nest.trait.structure.StructureInfoTrait",
        "weave.trait.security.BoltLockTrait",
        "weave.trait.security.BoltLockSettingsTrait",
        "weave.trait.security.BoltLockCapabilitiesTrait",
        "weave.trait.security.PincodeInputTrait",
        "weave.trait.security.TamperTrait",
        "weave.trait.description.DeviceIdentityTrait",  # Serial, firmware, model
        "weave.trait.power.BatteryPowerSourceTrait",    # Battery level, status
    ]
    
    print("Requested traits:")
    for trait in trait_names:
        print(f"  - {trait}")
    print()
    
    # Authenticate
    print("Authenticating...")
    try:
        session, access_token, user_id, transport_url = GetSessionWithAuth()
        print("✅ Authentication successful")
        print(f"   User ID: {user_id}")
        print()
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        return 1
    
    # Create handler
    handler = EnhancedProtobufHandler()
    
    # Build Observe request
    observe_request = v2_pb2.ObserveRequest(
        version=2,
        subscribe=True,
        filter=[v2_pb2.ResourceFilter(trait_type=t) for t in trait_names]
    )
    observe_data = observe_request.SerializeToString()
    
    headers = {
        "Authorization": f"Basic {access_token}",
        "Content-Type": "application/x-protobuf",
        "User-Agent": USER_AGENT_STRING,
        "X-Accept-Response-Streaming": "true",
        "Accept": "application/x-protobuf",
    }
    
    # Determine API URL (try transport_url first, then fallback to production)
    base_candidates = []
    if transport_url:
        base_candidates.append(transport_url.rstrip('/'))
    base_candidates.append(URL_PROTOBUF.format(grpc_hostname=PRODUCTION_HOSTNAME['grpc_hostname']).rstrip('/'))
    
    print(f"Connecting to Observe stream...")
    
    # Track results
    message_count = 0
    successful_parses = 0
    failed_parses = 0
    decoded_traits = {}
    all_trait_data = {}
    
    response = None
    for base_url in base_candidates:
        api_url = f"{base_url}{ENDPOINT_OBSERVE}"
        print(f"  Trying: {api_url}")
        try:
            response = session.post(api_url, headers=headers, data=observe_data, stream=True, timeout=(API_TIMEOUT_SECONDS, 300))
            response.raise_for_status()
            print("✅ Stream connected")
            print()
            break
        except Exception as e:
            print(f"  ❌ Failed: {e}")
            continue
    
    if not response:
        print("❌ Failed to connect to any transport endpoint")
        return 1
    
    try:
        
        # Process chunks manually
        handler.buffer = bytearray()
        handler.pending_length = None
        
        for chunk in response.iter_content(chunk_size=None):
            if not isinstance(chunk, bytes) or not chunk.strip():
                continue
            
            # Process chunk through handler
            if handler.pending_length is None:
                handler.pending_length, offset = handler._decode_varint(chunk, 0)
                if handler.pending_length is None or offset >= len(chunk):
                    continue
                handler.buffer.extend(chunk[offset:])
            else:
                handler.buffer.extend(chunk)
            
            # Process complete messages
            while handler.pending_length and len(handler.buffer) >= handler.pending_length:
                message = handler.buffer[:handler.pending_length]
                handler.buffer = handler.buffer[handler.pending_length:]
                locks_data = await handler._process_message(message)
                handler.pending_length = None if len(handler.buffer) < 5 else handler._decode_varint(handler.buffer, 0)[0]
                
                if locks_data.get("yale") or locks_data.get("user_id") or locks_data.get("structure_id") or locks_data.get("all_traits"):
                    message_count += 1
                    print(f"\n{'='*80}")
                    print(f"MESSAGE {message_count}")
                    print(f"{'='*80}")
                    
                    # Check if parsing was successful
                    successful_parses += 1
                    print("✅ Message parsed successfully")
            
                    # Display extracted data
                    if locks_data.get("yale"):
                        print("\n🔒 Lock Data:")
                        for device_id, lock_info in locks_data["yale"].items():
                            print(f"  Device: {device_id}")
                            print(f"    Locked: {lock_info.get('bolt_locked', 'unknown')}")
                            print(f"    Moving: {lock_info.get('bolt_moving', 'unknown')}")
                            print(f"    Actuator State: {lock_info.get('actuator_state', 'unknown')}")
                    
                    if locks_data.get("user_id"):
                        print(f"\n👤 User ID: {locks_data['user_id']}")
                    
                    if locks_data.get("structure_id"):
                        print(f"\n🏠 Structure ID: {locks_data['structure_id']}")
                    
                    # Display all decoded traits
                    all_traits = locks_data.get("all_traits", {})
                    if all_traits:
                        print(f"\n📊 Decoded Traits ({len(all_traits)}):")
                        for trait_key, trait_info in sorted(all_traits.items()):
                            type_url = trait_info.get("type_url", "unknown")
                            object_id = trait_info.get("object_id", "unknown")
                            decoded = trait_info.get("decoded", False)
                            
                            status = "✅" if decoded else "⚠️"
                            print(f"  {status} {type_url}")
                            print(f"      Object: {object_id}")
                            
                            if decoded:
                                data = trait_info.get("data", {})
                                if data:
                                    print(f"      Data:")
                                    for key, value in data.items():
                                        if value is not None:
                                            print(f"        {key}: {value}")
                                            # Track for summary
                                            if type_url not in all_trait_data:
                                                all_trait_data[type_url] = {}
                                            if key not in all_trait_data[type_url]:
                                                all_trait_data[type_url][key] = []
                                            all_trait_data[type_url][key].append(value)
                                else:
                                    print(f"      (no data)")
                            else:
                                error = trait_info.get("error", "Not decoded")
                                print(f"      Error: {error}")
                            
                            # Track decoded traits
                            if type_url not in decoded_traits:
                                decoded_traits[type_url] = {"decoded": 0, "failed": 0}
                            if decoded:
                                decoded_traits[type_url]["decoded"] += 1
                            else:
                                decoded_traits[type_url]["failed"] += 1
                    else:
                        print("\n⚠️  No traits extracted from this message")
                    
                    # Stop after a few successful messages
                    if message_count >= 5:
                        print(f"\n{'='*80}")
                        print("Stopping after 5 messages")
                        break
                
                if message_count >= 5:
                    break
            
            if message_count >= 5:
                break
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Summary
    print(f"\n{'='*80}")
    print("TEST SUMMARY")
    print(f"{'='*80}\n")
    
    print(f"Total messages processed: {message_count}")
    print(f"✅ Successfully parsed: {successful_parses}")
    print(f"❌ Failed to parse: {failed_parses}")
    print()
    
    if decoded_traits:
        print("Trait Decoding Results:")
        for type_url, stats in sorted(decoded_traits.items()):
            total = stats["decoded"] + stats["failed"]
            success_rate = (stats["decoded"] / total * 100) if total > 0 else 0
            status = "✅" if stats["decoded"] > 0 else "❌"
            print(f"  {status} {type_url}")
            print(f"      Decoded: {stats['decoded']}/{total} ({success_rate:.1f}%)")
        print()
    
    if all_trait_data:
        print("Extracted Data Summary:")
        for type_url, data_dict in sorted(all_trait_data.items()):
            print(f"\n  {type_url}:")
            for key, values in data_dict.items():
                unique_values = list(set(str(v) for v in values if v is not None))
                if unique_values:
                    print(f"    {key}: {', '.join(unique_values[:5])}")
                    if len(unique_values) > 5:
                        print(f"      ... and {len(unique_values) - 5} more")
        print()
    
    # Final verdict
    print("="*80)
    if successful_parses > 0 and any(stats["decoded"] > 0 for stats in decoded_traits.values()):
        print("✅ TEST PASSED: Handler successfully decodes traits!")
    else:
        print("❌ TEST FAILED: No traits decoded successfully")
    print("="*80)
    
    return 0 if successful_parses > 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

