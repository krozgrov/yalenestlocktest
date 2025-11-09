#!/usr/bin/env python3
"""
Live test of proto_decode.py with Nest URL.

This actually tests the general-purpose decoder fetching from Nest's endpoint.
"""

import subprocess
import sys
import json
import tempfile
from pathlib import Path

# Import Nest-specific modules
from dotenv import load_dotenv
import os
import requests
from proto.nestlabs.gateway import v2_pb2
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


def get_nest_auth():
    """Get Nest access token."""
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
    
    return access_token, user_id, transport_url


def build_observe_payload():
    """Build Nest Observe request payload."""
    req = v2_pb2.ObserveRequest(version=2, subscribe=True)
    trait_names = [
        "nest.trait.user.UserInfoTrait",
        "nest.trait.structure.StructureInfoTrait",
        "weave.trait.security.BoltLockTrait",
        "weave.trait.description.DeviceIdentityTrait",
        "weave.trait.power.BatteryPowerSourceTrait",
    ]
    for trait_name in trait_names:
        filt = req.filter.add()
        filt.trait_type = trait_name
    return req.SerializeToString()


def test_proto_decode_with_nest():
    """Test proto_decode.py with Nest URL."""
    print("=" * 80)
    print("TESTING GENERAL-PURPOSE DECODER WITH NEST URL")
    print("=" * 80)
    print()
    
    # Step 1: Authenticate
    print("Step 1: Authenticating with Nest...")
    try:
        access_token, user_id, transport_url = get_nest_auth()
        print(f"✅ Authenticated! User ID: {user_id}")
        print(f"   Transport URL: {transport_url}")
        print()
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        return 1
    
    # Step 2: Build payload
    print("Step 2: Building Observe request payload...")
    payload = build_observe_payload()
    print(f"✅ Payload built ({len(payload)} bytes)")
    print()
    
    # Step 3: Save to temp file
    with tempfile.NamedTemporaryFile(delete=False, suffix='.bin') as tmp:
        tmp.write(payload)
        temp_payload_path = tmp.name
    
    print(f"✅ Saved payload to temporary file")
    print()
    
    # Step 4: Build URL (use transport_url if available, otherwise fallback)
    if transport_url:
        # Use the transport URL from session
        base_url = transport_url.rstrip("/")
    else:
        # Fallback to production
        base_url = URL_PROTOBUF.format(grpc_hostname=PRODUCTION_HOSTNAME["grpc_hostname"])
    nest_url = f"{base_url}{ENDPOINT_OBSERVE}"
    
    print(f"Step 3: Using proto_decode.py with Nest URL")
    print(f"URL: {nest_url}")
    print()
    
    # Step 5: Build headers
    headers_dict = {
        "Authorization": f"Basic {access_token}",
        "Content-Type": "application/x-protobuf",
        "Accept": "application/x-protobuf",
        "X-Accept-Response-Streaming": "true",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "referer": "https://home.nest.com/",
        "origin": "https://home.nest.com",
        "X-Accept-Content-Transfer-Encoding": "binary"
    }
    headers_json = json.dumps(headers_dict)
    
    # Step 6: Build command
    cmd = [
        sys.executable, "proto_decode.py", "decode",
        "--url", nest_url,
        "--method", "POST",
        "--post-data", temp_payload_path,
        "--headers", headers_json,
        "--proto-path", "proto",
        "--message-type", "nest.rpc.StreamBody",
        "--format", "grpc-web",
        "--stream",
        "--timeout", "60",
        "--output", "pretty"
    ]
    
    print("Step 4: Running proto_decode.py...")
    print(f"Command: python proto_decode.py decode --url <NEST_URL> --method POST ...")
    print()
    print("=" * 80)
    print("DECODER OUTPUT:")
    print("=" * 80)
    print()
    
    try:
        # Run the decoder
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=45
        )
        
        # Print output
        if result.stdout:
            print(result.stdout)
        
        if result.stderr:
            print("Info/Warnings:", file=sys.stderr)
            print(result.stderr, file=sys.stderr)
        
        if result.returncode == 0:
            print()
            print("=" * 80)
            print("✅ SUCCESS! General-purpose decoder worked with Nest URL!")
            print("=" * 80)
        else:
            print()
            print("=" * 80)
            print(f"⚠️  Decoder returned code {result.returncode}")
            print("=" * 80)
            if result.stderr:
                print("Error output:")
                print(result.stderr)
            return 1
            
    except subprocess.TimeoutExpired:
        print("❌ Request timed out")
        return 1
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        # Cleanup
        try:
            Path(temp_payload_path).unlink()
        except:
            pass
    
    return 0


if __name__ == "__main__":
    sys.exit(test_proto_decode_with_nest())

