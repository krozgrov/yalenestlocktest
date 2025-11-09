#!/usr/bin/env python3
"""Decode all traits from Observe stream - simple version based on main.py."""

import asyncio
import json
import sys
import logging
from dotenv import load_dotenv
import os
import requests
from proto.nestlabs.gateway import v2_pb2
from protobuf_handler_enhanced import EnhancedProtobufHandler

# Suppress DecodeError logging - we'll handle it ourselves
logging.getLogger('protobuf_handler_enhanced').setLevel(logging.WARNING)
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

# Google Access Token
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

# Exchange Google Access Token for Nest JWT
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
nest_data = nest_response.json()
access_token = nest_data.get("jwt")

# Use Nest JWT to create session and get user ID and transport URL
session_url = "https://home.nest.com/session"
session_headers = {
    'User-Agent': USER_AGENT_STRING,
    'Authorization': f'Basic {access_token}',
    'cookie': f'G_ENABLED_IDPS=google; eu_cookie_accepted=1; viewer-volume=0.5; cztoken={access_token}',
    'timeout': f"{API_TIMEOUT_SECONDS}"
}
session_response = session.request("GET", session_url, headers=session_headers)
session_data = session_response.json()
access_token = session_data.get("access_token")
user_id = session_data.get("userid")
transport_url = session_data.get("urls").get("transport_url")

import sys
sys.stdout.flush()
sys.stderr.flush()

print("="*80, flush=True)
print("DECODING ALL TRAITS", flush=True)
print("="*80, flush=True)
print(flush=True)

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

def _normalize_base(url):
    return url.rstrip("/") if url else None

def _transport_candidates(session_base):
    candidates = []
    normalized_session = _normalize_base(session_base)
    if normalized_session:
        candidates.append(normalized_session)
    default = _normalize_base(URL_PROTOBUF.format(grpc_hostname=PRODUCTION_HOSTNAME["grpc_hostname"]))
    if default and default not in candidates:
        candidates.append(default)
    return candidates

# Connect to Observe stream
observe_response = None
for base_url in _transport_candidates(transport_url):
    target_url = f"{base_url}{ENDPOINT_OBSERVE}"
    try:
        print(f"Connecting to {target_url}...", flush=True)
        response = session.post(target_url, headers=headers_observe, data=payload_observe, stream=True, timeout=(API_TIMEOUT_SECONDS, API_TIMEOUT_SECONDS))
        response.raise_for_status()
        observe_response = response
        print("✅ Connected\n", flush=True)
        break
    except Exception as err:
        print(f"❌ Failed: {err}\n", flush=True)
        continue

if observe_response is None:
    session.close()
    print("❌ Failed to open Observe stream")
    sys.exit(1)

# Process with enhanced handler - use same approach as main.py
handler = EnhancedProtobufHandler()
message_count = 0
all_decoded_data = {}
locks_data = {"yale": {}, "user_id": None, "structure_id": None, "all_traits": {}}

print("Processing messages...\n", flush=True)

try:
    for chunk in observe_response.iter_content(chunk_size=None):
        if chunk:
            async def process_chunk(current_data):
                new_data = await handler._process_message(chunk)
                current_data.update(new_data)
                return current_data
            locks_data = asyncio.run(process_chunk(locks_data))
            
            # Check if we have any actual data
            has_data = False
            if locks_data.get("yale") and locks_data["yale"]:
                has_data = True
            if locks_data.get("user_id"):
                has_data = True
            if locks_data.get("structure_id"):
                has_data = True
            if locks_data.get("all_traits") and locks_data["all_traits"]:
                has_data = True
            
            # Process decoded message if we have data (show first complete message)
            if has_data:
                message_count += 1
                print(f"{'='*80}", flush=True)
                print(f"MESSAGE {message_count}", flush=True)
                print(f"{'='*80}", flush=True)
                
                if locks_data.get("yale"):
                    print("\n🔒 Lock Data:", flush=True)
                    for dev_id, info in locks_data["yale"].items():
                        print(f"  Device: {dev_id}", flush=True)
                        print(f"    Locked: {info.get('bolt_locked')}", flush=True)
                        print(f"    Moving: {info.get('bolt_moving')}", flush=True)
                
                if locks_data.get("user_id"):
                    print(f"\n👤 User ID: {locks_data['user_id']}", flush=True)
                
                if locks_data.get("structure_id"):
                    print(f"\n🏠 Structure ID: {locks_data['structure_id']}", flush=True)
                
                all_traits = locks_data.get("all_traits", {})
                if all_traits:
                    print(f"\n📊 Decoded Traits ({len(all_traits)}):", flush=True)
                    for trait_key, trait_info in sorted(all_traits.items()):
                        type_url = trait_info.get("type_url", "unknown")
                        object_id = trait_info.get("object_id", "unknown")
                        decoded = trait_info.get("decoded", False)
                        
                        status = "✅" if decoded else "⚠️"
                        trait_name = type_url.split('.')[-1] if type_url else "unknown"
                        print(f"\n  {status} {trait_name}", flush=True)
                        print(f"      Object: {object_id}", flush=True)
                        
                        if decoded:
                            data = trait_info.get("data", {})
                            if data:
                                print(f"      Data:", flush=True)
                                for key, value in data.items():
                                    if value is not None:
                                        # Format battery level as percentage
                                        if key == "battery_level" and isinstance(value, float):
                                            print(f"        {key}: {value * 100:.1f}%", flush=True)
                                        else:
                                            print(f"        {key}: {value}", flush=True)
                                        # Store for summary
                                        if trait_name not in all_decoded_data:
                                            all_decoded_data[trait_name] = {}
                                        if key not in all_decoded_data[trait_name]:
                                            all_decoded_data[trait_name][key] = []
                                        all_decoded_data[trait_name][key].append(value)
                            else:
                                print(f"      (no data)", flush=True)
                        else:
                            error = trait_info.get("error", "Not decoded")
                            print(f"      Error: {error}", flush=True)
                
                print(flush=True)
                observe_response.close()
                break
except (requests.exceptions.ConnectionError, requests.exceptions.ReadTimeout, TimeoutError) as e:
    # Expected - stream timeout after getting data
    pass
except KeyboardInterrupt:
    pass

session.close()

# Final Summary
print("="*80, flush=True)
print("FINAL SUMMARY", flush=True)
print("="*80, flush=True)
print(f"\nMessages processed: {message_count}", flush=True)
print(f"Traits decoded: {len(all_decoded_data)}", flush=True)

if all_decoded_data:
    print("\n📋 All Decoded Data:", flush=True)
    for trait_name, data_dict in sorted(all_decoded_data.items()):
        print(f"\n  {trait_name}:", flush=True)
        for key, values in data_dict.items():
            unique_values = list(set(str(v) for v in values if v is not None))
            if unique_values:
                print(f"    {key}: {', '.join(unique_values[:5])}", flush=True)
                if len(unique_values) > 5:
                    print(f"      ... and {len(unique_values) - 5} more", flush=True)

print("\n✅ DECODING COMPLETE", flush=True)

