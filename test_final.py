#!/usr/bin/env python3
"""Final working test - processes chunks directly like main.py."""

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
    print("FINAL TEST - ALL TRAIT DECODING")
    print("="*80)
    print()
    
    # Authenticate
    session, access_token, user_id, transport_url = GetSessionWithAuth()
    print("✅ Authenticated")
    
    # Build request
    req = v2_pb2.ObserveRequest(version=2, subscribe=True)
    trait_names = [
        "nest.trait.user.UserInfoTrait",
        "nest.trait.structure.StructureInfoTrait",
        "weave.trait.security.BoltLockTrait",
        "weave.trait.security.BoltLockSettingsTrait",
        "weave.trait.security.BoltLockCapabilitiesTrait",
        "weave.trait.security.PincodeInputTrait",
        "weave.trait.security.TamperTrait",
        "weave.trait.description.DeviceIdentityTrait",
        "weave.trait.power.BatteryPowerSourceTrait",
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
        except:
            continue
    
    if not response:
        print("❌ Connection failed")
        return 1
    
    # Process chunks
    handler = EnhancedProtobufHandler()
    message_count = 0
    decoded_traits = {}
    
    print("\nProcessing messages...\n")
    
    try:
        for chunk in response.iter_content(chunk_size=None):
            if not chunk or not chunk.strip():
                continue
            
            locks_data = await handler._process_message(chunk)
            
            if locks_data.get("yale") or locks_data.get("user_id") or locks_data.get("structure_id") or locks_data.get("all_traits"):
                message_count += 1
                print(f"Message {message_count}:")
                
                if locks_data.get("yale"):
                    for dev_id, info in locks_data["yale"].items():
                        print(f"  Lock: {dev_id} - Locked: {info.get('bolt_locked')}")
                
                if locks_data.get("user_id"):
                    print(f"  User ID: {locks_data['user_id']}")
                
                if locks_data.get("structure_id"):
                    print(f"  Structure ID: {locks_data['structure_id']}")
                
                all_traits = locks_data.get("all_traits", {})
                if all_traits:
                    print(f"  Traits decoded: {len(all_traits)}")
                    for trait_key, trait_info in all_traits.items():
                        if trait_info.get("decoded"):
                            type_url = trait_info.get("type_url", "")
                            data = trait_info.get("data", {})
                            print(f"    ✅ {type_url.split('.')[-1]}")
                            for key, value in data.items():
                                if value is not None:
                                    print(f"       {key}: {value}")
                            
                            type_name = type_url.split('.')[-1]
                            if type_name not in decoded_traits:
                                decoded_traits[type_name] = []
                            decoded_traits[type_name].append(data)
                
                print()
                
                if message_count >= 3:
                    break
    
    except KeyboardInterrupt:
        pass
    finally:
        response.close()
    
    # Summary
    print("="*80)
    print("SUMMARY")
    print("="*80)
    print(f"Messages: {message_count}")
    print(f"Traits decoded: {len(decoded_traits)}")
    for trait_name, data_list in decoded_traits.items():
        print(f"\n{trait_name}:")
        for data in data_list:
            for key, value in data.items():
                if value is not None:
                    print(f"  {key}: {value}")
    
    print("\n✅ TEST COMPLETE")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

