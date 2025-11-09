#!/usr/bin/env python3
"""
Capture messages with HomeKit traits and save raw messages for analysis.
This avoids the proto pool issues by saving raw data first.
"""

import base64
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
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

if not ISSUE_TOKEN or not COOKIES:
    print("Error: ISSUE_TOKEN and COOKIES must be set in .env file")
    sys.exit(1)


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


def main():
    # HomeKit-relevant traits
    trait_names = [
        "nest.trait.user.UserInfoTrait",
        "nest.trait.structure.StructureInfoTrait",
        "weave.trait.security.BoltLockTrait",
        "weave.trait.security.BoltLockSettingsTrait",
        "weave.trait.security.BoltLockCapabilitiesTrait",
        "weave.trait.security.PincodeInputTrait",
        "weave.trait.security.TamperTrait",
        # HomeKit traits
        "weave.trait.description.DeviceIdentityTrait",  # Serial, firmware, model
        "weave.trait.power.BatteryPowerSourceTrait",    # Battery level, status
    ]
    
    print("="*80)
    print("CAPTURING MESSAGES WITH HOMEKIT TRAITS")
    print("="*80)
    print()
    print("Traits:")
    for trait in trait_names:
        print(f"  - {trait}")
    print()
    
    # Prepare capture directory
    output_dir = Path("captures")
    output_dir.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    capture_dir = output_dir / f"{timestamp}_homekit_traits"
    capture_dir.mkdir(exist_ok=True)
    
    print(f"Capture directory: {capture_dir}")
    print()
    
    # Authenticate (same as main.py)
    print("Authenticating...")
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
    
    print("✅ Authentication successful")
    print()
    
    # Build Observe Request
    req = v2_pb2.ObserveRequest(version=2, subscribe=True)
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
        print("❌ Failed to open Observe stream")
        return 1
    
    print("✅ Observe stream connected")
    print()
    
    # Process and save messages
    handler = NestProtobufHandler()
    chunk_count = 0
    limit = 5
    
    print(f"Capturing up to {limit} messages...")
    print()
    
    try:
        import asyncio
        for chunk in observe_response.iter_content(chunk_size=None):
            if not chunk:
                continue
            
            # Save raw message
            raw_file = capture_dir / f"{chunk_count+1:05d}.raw.bin"
            with open(raw_file, "wb") as f:
                f.write(chunk)
            
            # Process message
            async def process():
                return await handler._process_message(chunk)
            
            locks_data = asyncio.run(process())
            
            if locks_data.get("yale") or locks_data.get("user_id") or locks_data.get("structure_id"):
                chunk_count += 1
                print(f"✅ Captured message {chunk_count}")
                
                # Save decoded data as JSON
                decoded_file = capture_dir / f"{chunk_count:05d}.decoded.json"
                with open(decoded_file, "w") as f:
                    json.dump(locks_data, f, indent=2, default=str)
                
                # Print what we found
                if locks_data.get("yale"):
                    for device_id, device_data in locks_data["yale"].items():
                        print(f"   Device: {device_id}")
                        if device_data.get("serial_number"):
                            print(f"   ✅ Serial Number: {device_data['serial_number']}")
                        if device_data.get("firmware_version"):
                            print(f"   ✅ Firmware: {device_data['firmware_version']}")
                        if device_data.get("battery_level"):
                            print(f"   ✅ Battery: {device_data['battery_level']}%")
                
                if chunk_count >= limit:
                    break
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    # Save metadata
    metadata = {
        "traits": trait_names,
        "chunk_count": chunk_count,
        "timestamp": datetime.now().isoformat(),
    }
    with open(capture_dir / "manifest.json", "w") as f:
        json.dump(metadata, f, indent=2)
    
    print()
    print("="*80)
    print("CAPTURE COMPLETE")
    print("="*80)
    print(f"Captured {chunk_count} message(s)")
    print(f"Location: {capture_dir}")
    print()
    print("Next steps:")
    print(f"  1. python find_serial_number.py AHNJ2005298 --captures-dir {capture_dir}")
    print(f"  2. python extract_all_homekit_data.py --capture-dir {capture_dir}")
    
    session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

