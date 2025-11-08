#!/usr/bin/env python3
"""
Test the enhanced protobuf handler with all trait decoders.

This uses main.py's approach but shows all decoded traits.
"""

import json
import asyncio
from dotenv import load_dotenv
import os
import requests
from proto.nestlabs.gateway import v2_pb2
from protobuf_handler import NestProtobufHandler
from const import (
    API_TIMEOUT_SECONDS,
    USER_AGENT_STRING,
    ENDPOINT_OBSERVE,
    URL_PROTOBUF,
    PRODUCTION_HOSTNAME
)

load_dotenv()

ISSUE_TOKEN = os.environ.get("ISSUE_TOKEN")
COOKIES = os.environ.get("COOKIES")

def _normalize_base(url: str | None) -> str | None:
    if not url:
        return None
    return url.rstrip("/")

def _transport_candidates(session_base: str | None) -> list[str]:
    candidates = []
    normalized_session = _normalize_base(session_base)
    if normalized_session:
        candidates.append(normalized_session)
    default = _normalize_base(URL_PROTOBUF.format(grpc_hostname=PRODUCTION_HOSTNAME["grpc_hostname"]))
    if default and default not in candidates:
        candidates.append(default)
    return candidates

# Authenticate
headers = {
    'Sec-Fetch-Mode': 'cors',
    'X-Requested-With': 'XmlHttpRequest',
    'Referer': 'https://accounts.google.com/o/oauth2/iframe',
    'cookie': COOKIES,
    'User-Agent': USER_AGENT_STRING,
    'timeout': f"{API_TIMEOUT_SECONDS}",
}
response = requests.request("GET", ISSUE_TOKEN, headers=headers)
google_access_token = response.json().get("access_token")
session = requests.Session()

nest_url = "https://nestauthproxyservice-pa.googleapis.com/v1/issue_jwt"
nest_headers = {
    'Authorization': f'Bearer {google_access_token}',
    'User-Agent': USER_AGENT_STRING,
    'Referer': URL_PROTOBUF,
    'timeout': f"{API_TIMEOUT_SECONDS}"
}
nest_response = session.request("POST", nest_url, headers=nest_headers, json={
    "embed_google_oauth_access_token": "true",
    "expire_after": "3600s",
    "google_oauth_access_token": google_access_token,
    "policy_id": "authproxy-oauth-policy"
})
access_token = nest_response.json().get("jwt")

session_url = "https://home.nest.com/session"
session_headers = {
    'Authorization': f'Basic {access_token}',
    'User-Agent': USER_AGENT_STRING,
    'Referer': 'https://home.nest.com/',
    'timeout': f"{API_TIMEOUT_SECONDS}"
}
session_response = session.post(session_url, headers=session_headers)
session_data = session_response.json()
transport_url = session_data.get("urls", {}).get("transport_url")

# Build Observe Request
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
payload_observe = req.SerializeToString()

# Send Observe request
headers_observe = {
    'Accept-Encoding': 'gzip, deflate, br, zstd',
    'Content-Type': 'application/x-protobuf',
    'User-Agent': USER_AGENT_STRING,
    'X-Accept-Response-Streaming': 'true',
    'Accept': 'application/x-protobuf',
    'referer': 'https://home.nest.com/',
    'origin': 'https://home.nest.com',
    'X-Accept-Content-Transfer-Encoding': 'binary',
    'Authorization': 'Basic ' + access_token
}

observe_response = None
for base_url in _transport_candidates(transport_url):
    target_url = f"{base_url}{ENDPOINT_OBSERVE}"
    try:
        print(f"Sending Observe request to {target_url}")
        response = session.post(target_url, headers=headers_observe, data=payload_observe, stream=True, timeout=(API_TIMEOUT_SECONDS, API_TIMEOUT_SECONDS))
        response.raise_for_status()
        observe_response = response
        break
    except Exception as err:
        print(f"Failed for {target_url}: {err}")
        continue

if observe_response is None:
    session.close()
    raise SystemExit("Failed to open Observe stream")

print("✅ Observe stream connected\n")

handler = NestProtobufHandler()
message_count = 0
max_messages = 3

print("="*80)
print("TESTING ENHANCED HANDLER - ALL TRAIT DECODING")
print("="*80)
print()

for chunk in observe_response.iter_content(chunk_size=None):
    if chunk:
        async def process_chunk():
            return await handler._process_message(chunk)
        
        locks_data = asyncio.run(process_chunk())
        
        # Check if we got useful data
        if locks_data.get("yale") or locks_data.get("user_id") or locks_data.get("structure_id") or locks_data.get("all_traits"):
            message_count += 1
            print(f"Message {message_count}:")
            
            if locks_data.get("yale"):
                print("  Lock Data:")
                for device_id, device_data in locks_data["yale"].items():
                    print(f"    Device: {device_id}")
                    for key, value in device_data.items():
                        print(f"      {key}: {value}")
            
            if locks_data.get("user_id"):
                print(f"  User ID: {locks_data['user_id']}")
            if locks_data.get("structure_id"):
                print(f"  Structure ID: {locks_data['structure_id']}")
            
            # Show all decoded traits
            all_traits = locks_data.get("all_traits", {})
            if all_traits:
                print(f"\n  Decoded Traits ({len(all_traits)}):")
                decoded_count = 0
                for trait_key, trait_info in sorted(all_traits.items()):
                    type_url = trait_info["type_url"]
                    obj_id = trait_info["object_id"]
                    
                    if trait_info.get("decoded"):
                        decoded_count += 1
                        print(f"    ✅ {type_url}")
                        print(f"       Object ID: {obj_id}")
                        for key, value in trait_info.get("data", {}).items():
                            if value is not None:
                                print(f"       {key}: {value}")
                    elif "error" in trait_info:
                        print(f"    ❌ {type_url}: {trait_info['error']}")
                    else:
                        print(f"    ⚠️  {type_url}: No decoder")
                print(f"\n  Summary: {decoded_count}/{len(all_traits)} traits decoded successfully")
            else:
                print("  ⚠️  No traits extracted")
            
            print()
            
            if message_count >= max_messages:
                observe_response.close()
                break

print("="*80)
print("TEST COMPLETE")
print("="*80)

session.close()

