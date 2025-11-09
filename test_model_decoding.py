#!/usr/bin/env python3
"""
Test script to verify model decoding from DeviceIdentityTrait.

This script specifically focuses on ensuring the model field is correctly
extracted from the protobuf messages.
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
    print("MODEL DECODING TEST")
    print("="*80)
    print()
    print("This test verifies that the model field is correctly decoded")
    print("from DeviceIdentityTrait. Expected model: 'Next x Yale Lock-1.1'")
    print()
    
    # Authenticate
    try:
        session, access_token, user_id, transport_url = GetSessionWithAuth()
        print("✅ Authenticated")
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        return 1
    
    # Build request with DeviceIdentityTrait
    req = v2_pb2.ObserveRequest(version=2, subscribe=True)
    trait_names = [
        "weave.trait.description.DeviceIdentityTrait",  # Required for model
        "weave.trait.security.BoltLockTrait",  # For device identification
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
    message_count = 0
    yale_lock_device_id = "DEVICE_00177A0000060303"
    yale_model_found = False
    all_devices_seen = set()
    
    print("\nProcessing messages...")
    print(f"Looking specifically for Yale lock: {yale_lock_device_id}\n")
    
    try:
        for chunk in response.iter_content(chunk_size=None):
            if not chunk or not chunk.strip():
                continue
            
            locks_data = await handler._process_message(chunk)
            
            # Check for DeviceIdentityTrait - focus on Yale lock
            all_traits = locks_data.get("all_traits", {})
            if all_traits:
                for trait_key, trait_info in all_traits.items():
                    # Only check traits for the Yale lock device
                    if yale_lock_device_id in trait_key and "DeviceIdentityTrait" in trait_key:
                        message_count += 1
                        print(f"📦 Message {message_count}: Found DeviceIdentityTrait for YALE LOCK")
                        print(f"   Trait key: {trait_key}")
                        
                        if trait_info.get("decoded"):
                            data = trait_info.get("data", {})
                            print("   ✅ Successfully decoded!")
                            
                            # Check each field
                            if data.get("serial_number"):
                                print(f"   📝 Serial Number: {data['serial_number']}")
                            else:
                                print("   ⚠️  Serial Number: Not found")
                            
                            if data.get("firmware_version"):
                                print(f"   📝 Firmware Version: {data['firmware_version']}")
                            else:
                                print("   ⚠️  Firmware Version: Not found")
                            
                            if data.get("manufacturer"):
                                print(f"   📝 Manufacturer: {data['manufacturer']}")
                            else:
                                print("   ⚠️  Manufacturer: Not found")
                            
                            # CRITICAL: Check model
                            if data.get("model"):
                                model_value = data["model"]
                                print(f"   ✅ MODEL: {model_value}")
                                yale_model_found = True
                                
                                # Verify it matches expected
                                if "Next x Yale Lock" in model_value or "Yale Lock" in model_value or "Linus" in model_value:
                                    print(f"   ✅ Model matches expected pattern!")
                                else:
                                    print(f"   ⚠️  Model doesn't match expected pattern")
                            else:
                                print("   ❌ MODEL: NOT FOUND")
                                print("   This is the issue we need to fix!")
                                
                                # Debug: Check if model_name field exists but is empty
                                type_url = trait_info.get("type_url", "")
                                print(f"   Debug: type_url = {type_url}")
                                print(f"   Debug: trait_info keys = {list(trait_info.keys())}")
                                print(f"   Debug: data keys = {list(data.keys())}")
                        else:
                            error = trait_info.get("error", "Unknown error")
                            print(f"   ❌ Decoding failed: {error}")
                        
                        print()
                    
                    # Track all devices we see
                    obj_id = trait_info.get("object_id", "")
                    if obj_id and obj_id.startswith("DEVICE_"):
                        all_devices_seen.add(obj_id)
                
                # Also check if we see the Yale lock in other traits
                if yale_lock_device_id in locks_data.get("yale", {}):
                    print(f"✅ Yale lock found in lock data: {yale_lock_device_id}")
                    lock_info = locks_data["yale"][yale_lock_device_id]
                    print(f"   Lock state: {lock_info}")
                    print()
                
                if yale_model_found:
                    break
                
                # Show progress - what devices we've seen
                if len(all_devices_seen) > 0 and message_count == 0:
                    print(f"   Devices seen so far: {', '.join(sorted(all_devices_seen))}")
                    if yale_lock_device_id not in all_devices_seen:
                        print(f"   ⚠️  Yale lock ({yale_lock_device_id}) not yet seen in messages")
                    print()
        
        if message_count == 0:
            print("⚠️  No DeviceIdentityTrait messages found")
            print("   This might mean:")
            print("   1. The device hasn't sent DeviceIdentityTrait yet")
            print("   2. The trait filter isn't working")
            print("   3. The message format is different")
            
            # Show what traits we did find
            if all_traits:
                print(f"\n   Found {len(all_traits)} other traits:")
                for trait_key in list(all_traits.keys())[:5]:
                    print(f"     - {trait_key}")
    
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
    print(f"Messages processed for Yale lock: {message_count}")
    print(f"Yale lock model found: {'✅ YES' if yale_model_found else '❌ NO'}")
    print(f"All devices seen: {len(all_devices_seen)}")
    if all_devices_seen:
        print(f"   Device IDs: {', '.join(sorted(all_devices_seen))}")
    
    if yale_model_found:
        print("\n✅ SUCCESS: Yale lock model decoding is working!")
    else:
        print("\n❌ FAILURE: Yale lock model was not decoded")
        print(f"\nThe Yale lock device ({yale_lock_device_id}) was found, but the model_name field")
        print("is not present in its DeviceIdentityTrait message.")
        print("\nPossible reasons:")
        print("1. The device may not send model_name in DeviceIdentityTrait")
        print("2. The model might be in a different trait or message")
        print("3. The model might come in a later message (need to wait longer)")
        print("4. The API might require a different request to get model info")
        print("\nNext steps:")
        print("1. Check if model is in other traits (check all_traits output)")
        print("2. Wait longer for more messages")
        print("3. Check raw protobuf captures for model information")
        print("4. Look for model in device metadata or other sources")
    
    return 0 if yale_model_found else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

