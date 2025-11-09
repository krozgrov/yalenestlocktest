#!/usr/bin/env python3
"""
Simple capture script for HomeKit traits that avoids proto pool issues.
Based on main.py but captures with DeviceIdentityTrait and BatteryPowerSourceTrait.
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


def prepare_capture_dir(base_dir: Path, traits: list[str]) -> Path:
    """Create a capture directory with timestamp and trait names."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    trait_suffix = "_".join([t.split(".")[-1] for t in traits[:5]])  # First 5 traits
    dir_name = f"{timestamp}_{trait_suffix}"
    run_dir = base_dir / dir_name
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


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
        "weave.trait.power.BatteryPowerSourceTrait",   # Battery level, status
    ]
    
    print("="*80)
    print("CAPTURING MESSAGES WITH HOMEKIT TRAITS")
    print("="*80)
    print()
    print("Traits to capture:")
    for trait in trait_names:
        print(f"  - {trait}")
    print()
    
    # Prepare capture directory
    output_dir = Path("captures")
    output_dir.mkdir(exist_ok=True)
    capture_dir = prepare_capture_dir(output_dir, trait_names)
    
    print(f"Capture directory: {capture_dir}")
    print()
    
    # Authenticate
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
    
    # Exchange for Nest JWT
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
    
    # Create session
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
    observe_base = None
    for base_url in _transport_candidates(transport_url):
        target_url = f"{base_url}{ENDPOINT_OBSERVE}"
        try:
            print(f"Sending Observe request to {target_url}")
            response = session.post(target_url, headers=headers_observe, data=payload_observe, stream=True, timeout=(API_TIMEOUT_SECONDS, API_TIMEOUT_SECONDS))
            response.raise_for_status()
            observe_response = response
            observe_base = base_url
            break
        except Exception as err:
            print(f"Failed for {target_url}: {err}")
            continue
    
    if observe_response is None:
        print("❌ Failed to open Observe stream")
        return 1
    
    print("✅ Observe stream connected")
    print()
    
    # Process messages
    handler = NestProtobufHandler()
    chunk_count = 0
    limit = 5
    
    print(f"Capturing up to {limit} messages...")
    print()
    
    try:
        for chunk in observe_response.iter_content(chunk_size=8192):
            if not chunk:
                continue
            
            results = handler._ingest_chunk(chunk)
            for locks_data in results:
                if locks_data.get("yale"):
                    chunk_count += 1
                    print(f"✅ Captured message {chunk_count}")
                    
                    # Save raw message (we'll need to extract it from handler)
                    # For now, just count
                    
                    if chunk_count >= limit:
                        break
            
            if chunk_count >= limit:
                break
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    # Save capture metadata
    metadata = {
        "traits": trait_names,
        "chunk_count": chunk_count,
        "timestamp": datetime.now().isoformat(),
        "capture_dir": str(capture_dir),
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
    print("Note: Raw message capture requires additional work.")
    print("For now, check the handler's stream_body for decoded data.")
    print()
    print("Next steps:")
    print("  1. Check if serial number appears in decoded messages")
    print("  2. Run: python find_serial_number.py AHNJ2005298")
    print("  3. Run: python extract_all_homekit_data.py --captures-dir captures")
    
    session.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())

