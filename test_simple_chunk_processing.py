#!/usr/bin/env python3
"""
Simple test: process chunks directly like main.py does.

This bypasses the stream() method's varint extraction and processes
chunks directly as StreamBody messages.
"""

import asyncio
import json
import sys
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


async def main():
    load_dotenv()
    
    print("="*80)
    print("SIMPLE CHUNK PROCESSING TEST")
    print("="*80)
    print()
    
    # Authenticate
    print("Authenticating...")
    try:
        session, access_token, user_id, transport_url = GetSessionWithAuth()
        print("✅ Authentication successful")
        print()
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        return 1
    
    # Build Observe request
    trait_names = [
        "nest.trait.user.UserInfoTrait",
        "nest.trait.structure.StructureInfoTrait",
        "weave.trait.security.BoltLockTrait",
        "weave.trait.description.DeviceIdentityTrait",
        "weave.trait.power.BatteryPowerSourceTrait",
    ]
    
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
    
    # Determine API URL
    base_candidates = []
    if transport_url:
        base_candidates.append(transport_url.rstrip('/'))
    base_candidates.append(URL_PROTOBUF.format(grpc_hostname=PRODUCTION_HOSTNAME['grpc_hostname']).rstrip('/'))
    
    response = None
    api_url = None
    
    for base_url in base_candidates:
        api_url = f"{base_url}{ENDPOINT_OBSERVE}"
        try:
            response = requests.post(
                api_url,
                headers=headers,
                data=observe_data,
                stream=True,
                timeout=(API_TIMEOUT_SECONDS, 10),
            )
            response.raise_for_status()
            print(f"✅ Connected to {api_url}")
            break
        except Exception as e:
            print(f"  ❌ Failed: {e}")
            continue
    
    if not response:
        print("❌ Failed to connect")
        return 1
    
    print()
    print("Processing chunks directly (like main.py)...")
    print()
    
    handler = EnhancedProtobufHandler()
    message_count = 0
    decoded_traits = {}
    all_trait_data = {}
    
    try:
        for chunk in response.iter_content(chunk_size=None):
            if not chunk or not chunk.strip():
                continue
            
            # Process chunk directly (like main.py does)
            locks_data = await handler._process_message(chunk)
            
            if locks_data.get("yale") or locks_data.get("user_id") or locks_data.get("structure_id") or locks_data.get("all_traits"):
                message_count += 1
                print(f"\n{'='*80}")
                print(f"MESSAGE {message_count}")
                print(f"{'='*80}")
                print("✅ Message parsed successfully")
                
                # Display data
                if locks_data.get("yale"):
                    print("\n🔒 Lock Data:")
                    for device_id, lock_info in locks_data["yale"].items():
                        print(f"  Device: {device_id}")
                        print(f"    Locked: {lock_info.get('bolt_locked', 'unknown')}")
                
                if locks_data.get("user_id"):
                    print(f"\n👤 User ID: {locks_data['user_id']}")
                
                if locks_data.get("structure_id"):
                    print(f"\n🏠 Structure ID: {locks_data['structure_id']}")
                
                # Display decoded traits
                all_traits = locks_data.get("all_traits", {})
                if all_traits:
                    print(f"\n📊 Decoded Traits ({len(all_traits)}):")
                    for trait_key, trait_info in sorted(all_traits.items()):
                        type_url = trait_info.get("type_url", "unknown")
                        decoded = trait_info.get("decoded", False)
                        
                        status = "✅" if decoded else "⚠️"
                        print(f"  {status} {type_url}")
                        
                        if decoded:
                            data = trait_info.get("data", {})
                            for key, value in data.items():
                                if value is not None:
                                    print(f"      {key}: {value}")
                                    if type_url not in all_trait_data:
                                        all_trait_data[type_url] = {}
                                    if key not in all_trait_data[type_url]:
                                        all_trait_data[type_url][key] = []
                                    all_trait_data[type_url][key].append(value)
                            
                            if type_url not in decoded_traits:
                                decoded_traits[type_url] = {"decoded": 0, "failed": 0}
                            decoded_traits[type_url]["decoded"] += 1
                        else:
                            if type_url not in decoded_traits:
                                decoded_traits[type_url] = {"decoded": 0, "failed": 0}
                            decoded_traits[type_url]["failed"] += 1
                
                if message_count >= 5:
                    print(f"\n{'='*80}")
                    print("Stopping after 5 messages")
                    break
    
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        response.close()
    
    # Summary
    print(f"\n{'='*80}")
    print("SUMMARY")
    print(f"{'='*80}\n")
    print(f"Messages processed: {message_count}")
    
    if decoded_traits:
        print("\nTrait Decoding:")
        for type_url, stats in sorted(decoded_traits.items()):
            total = stats["decoded"] + stats["failed"]
            print(f"  {type_url}: {stats['decoded']}/{total} decoded")
    
    if all_trait_data:
        print("\nExtracted Data:")
        for type_url, data_dict in sorted(all_trait_data.items()):
            print(f"\n  {type_url}:")
            for key, values in data_dict.items():
                unique = list(set(str(v) for v in values if v is not None))
                if unique:
                    print(f"    {key}: {', '.join(unique[:3])}")
    
    print()
    return 0 if message_count > 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

