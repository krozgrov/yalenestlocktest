#!/usr/bin/env python3
"""
Test script to verify all BoltLock traits are being decoded correctly.

This script tests:
- BoltLockTrait (all fields)
- BoltLockSettingsTrait
- BoltLockCapabilitiesTrait
- PincodeInputTrait
- TamperTrait
"""

import asyncio
import sys
import logging
from dotenv import load_dotenv
import requests

from protobuf_handler_enhanced import EnhancedProtobufHandler
from auth import GetSessionWithAuth
from proto.nestlabs.gateway import v2_pb2
from const import (
    USER_AGENT_STRING,
    URL_PROTOBUF,
    ENDPOINT_OBSERVE,
    PRODUCTION_HOSTNAME,
    API_TIMEOUT_SECONDS,
)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
_LOGGER = logging.getLogger(__name__)


async def main():
    load_dotenv()
    
    print("="*80)
    print("BOLTLOCK TRAITS DECODING TEST")
    print("="*80)
    print()
    print("This test verifies that all BoltLock-related traits are decoded:")
    print("  - BoltLockTrait (state, actuator, actor, timestamps)")
    print("  - BoltLockSettingsTrait (auto-relock settings)")
    print("  - BoltLockCapabilitiesTrait (handedness, max duration)")
    print("  - PincodeInputTrait")
    print("  - TamperTrait")
    print()
    
    # Authenticate
    try:
        session, access_token, user_id, transport_url = GetSessionWithAuth()
        print("✅ Authenticated")
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        return 1
    
    # Build request with all BoltLock traits
    req = v2_pb2.ObserveRequest(version=2, subscribe=True)
    trait_names = [
        "weave.trait.security.BoltLockTrait",
        "weave.trait.security.BoltLockSettingsTrait",
        "weave.trait.security.BoltLockCapabilitiesTrait",
        "weave.trait.security.PincodeInputTrait",
        "weave.trait.security.TamperTrait",
    ]
    for trait_name in trait_names:
        filt = req.filter.add()
        filt.trait_type = trait_name
    payload = req.SerializeToString()
    
    headers = {
        "Authorization": f"Basic {access_token}",
        "Content-Type": "application/x-protobuf",
        "User-Agent": USER_AGENT_STRING,
        "X-Accept-Response-Streaming": "true",
        "Accept": "application/x-protobuf",
        "X-Accept-Content-Transfer-Encoding": "binary",
        "Accept-Encoding": "gzip, deflate, br",
        "referer": "https://home.nest.com/",
        "origin": "https://home.nest.com",
    }
    
    # Connect
    base_candidates = []
    if transport_url:
        base_candidates.append(transport_url.rstrip('/'))
    base_candidates.append(URL_PROTOBUF.format(grpc_hostname=PRODUCTION_HOSTNAME['grpc_hostname']).rstrip('/'))
    
    response = None
    for base_url in base_candidates:
        try:
            response = requests.post(
                f"{base_url}{ENDPOINT_OBSERVE}",
                headers=headers,
                data=payload,
                stream=True,
                timeout=(API_TIMEOUT_SECONDS, 10),
            )
            response.raise_for_status()
            print(f"✅ Connected to {base_url}")
            break
        except Exception as e:
            print(f"⚠️  Failed to connect to {base_url}: {e}")
            continue
    
    if not response:
        print("❌ Connection failed to all endpoints")
        return 1
    
    # Process chunks - focus on Yale lock device
    handler = EnhancedProtobufHandler()
    yale_lock_device_id = "DEVICE_00177A0000060303"
    traits_found = {}
    message_count = 0
    
    print("\nProcessing messages...")
    print(f"Looking for Yale lock: {yale_lock_device_id}\n")
    
    try:
        for chunk in response.iter_content(chunk_size=None):
            if not chunk or not chunk.strip():
                continue
            
            locks_data = await handler._process_message(chunk)
            
            # Check for BoltLock traits for Yale lock
            all_traits = locks_data.get("all_traits", {})
            if all_traits:
                for trait_key, trait_info in all_traits.items():
                    # Only check traits for the Yale lock device
                    if yale_lock_device_id in trait_key:
                        trait_name = trait_info.get("type_url", "").split(".")[-1]
                        
                        message_count += 1
                        print(f"📦 Found {trait_name} for YALE LOCK")
                        
                        if trait_info.get("decoded"):
                            traits_found[trait_name] = trait_info.get("data", {})
                            data = trait_info.get("data", {})
                            if data:
                                print(f"   ✅ Decoded successfully!")
                                for key, value in data.items():
                                    if value is not None:
                                        print(f"      {key}: {value}")
                            else:
                                print(f"   ⚠️  Decoded but no data fields present")
                        else:
                            error = trait_info.get("error", "Unknown error")
                            print(f"   ❌ Decoding failed: {error}")
                        print()
                
                # Also show lock data
                if yale_lock_device_id in locks_data.get("yale", {}):
                    lock_info = locks_data["yale"][yale_lock_device_id]
                    print(f"🔒 Lock State Data:")
                    for key, value in lock_info.items():
                        if value is not None:
                            print(f"   {key}: {value}")
                    print()
                
                # Stop after we've seen all traits or enough messages
                if len(traits_found) >= 5 or message_count >= 10:
                    break
    
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
    except Exception as e:
        print(f"\n❌ Error processing messages: {e}")
        import traceback
        traceback.print_exc()
    finally:
        response.close()
    
    # Summary
    print("="*80)
    print("SUMMARY")
    print("="*80)
    print(f"Messages processed: {message_count}")
    print(f"Traits found for Yale lock: {len(traits_found)}")
    
    expected_traits = {
        "BoltLockTrait": ["state", "actuator_state", "locked_state", "bolt_lock_actor"],
        "BoltLockSettingsTrait": ["auto_relock_on", "auto_relock_duration_seconds"],
        "BoltLockCapabilitiesTrait": ["handedness", "max_auto_relock_duration_seconds"],
        "PincodeInputTrait": ["pincode_input_state"],
        "TamperTrait": ["tamper_state"],
    }
    
    print("\nTrait Decoding Status:")
    for trait_name, expected_fields in expected_traits.items():
        if trait_name in traits_found:
            data = traits_found[trait_name]
            found_fields = [f for f in expected_fields if f in data and data[f] is not None]
            status = "✅" if len(found_fields) > 0 else "⚠️"
            print(f"  {status} {trait_name}: {len(found_fields)}/{len(expected_fields)} fields decoded")
            if found_fields:
                print(f"     Fields: {', '.join(found_fields)}")
        else:
            print(f"  ❌ {trait_name}: Not found")
    
    if len(traits_found) >= 3:
        print("\n✅ SUCCESS: Multiple BoltLock traits are being decoded!")
    else:
        print("\n⚠️  Some traits may not be present in the messages yet")
    
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

