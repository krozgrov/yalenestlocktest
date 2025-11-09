#!/usr/bin/env python3
"""
Test the general-purpose decoder with Nest using URL support.

This demonstrates how to use proto_decode.py with Nest's actual endpoint.
"""

import subprocess
import sys
import json
import base64
from pathlib import Path

from auth import GetSessionWithAuth
from const import ENDPOINT_OBSERVE, URL_PROTOBUF, PRODUCTION_HOSTNAME
from proto.nestlabs.gateway import v2_pb2


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


def test_nest_with_url():
    """Test proto_decode.py with Nest URL."""
    print("=" * 80)
    print("TESTING GENERAL-PURPOSE DECODER WITH NEST")
    print("=" * 80)
    print()
    
    # Get authentication
    print("Step 1: Authenticating with Nest...")
    try:
        session, access_token, user_id, transport_url = GetSessionWithAuth()
        print(f"✅ Authenticated! User ID: {user_id}")
        print()
    except Exception as e:
        print(f"❌ Authentication failed: {e}")
        return 1
    
    # Build Observe request
    print("Step 2: Building Observe request payload...")
    payload = build_observe_payload()
    print(f"✅ Payload built ({len(payload)} bytes)")
    print()
    
    # Save payload to temp file
    temp_payload = Path("temp_observe_request.bin")
    temp_payload.write_bytes(payload)
    print(f"✅ Saved payload to {temp_payload}")
    print()
    
    # Determine URL
    base_url = URL_PROTOBUF.format(grpc_hostname=PRODUCTION_HOSTNAME["grpc_hostname"])
    nest_url = f"{base_url}{ENDPOINT_OBSERVE}"
    
    print(f"Step 3: Fetching from Nest endpoint...")
    print(f"URL: {nest_url}")
    print()
    
    # Build headers JSON
    headers_json = json.dumps({
        "Authorization": f"Basic {access_token}",
        "Content-Type": "application/x-protobuf",
        "Accept": "application/x-protobuf",
        "X-Accept-Response-Streaming": "true",
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "referer": "https://home.nest.com/",
        "origin": "https://home.nest.com",
        "X-Accept-Content-Transfer-Encoding": "binary"
    })
    
    # Build proto_decode.py command
    cmd = [
        "python", "proto_decode.py", "decode",
        "--url", nest_url,
        "--method", "POST",
        "--post-data", str(temp_payload),
        "--headers", headers_json,
        "--proto-path", "proto",
        "--message-type", "nest.rpc.StreamBody",
        "--format", "grpc-web",
        "--stream",
        "--timeout", "30",
        "--output", "pretty"
    ]
    
    print("Step 4: Running proto_decode.py...")
    print(f"Command: {' '.join(cmd[:8])} ... [headers] ...")
    print()
    
    try:
        # Run the decoder
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        if result.returncode == 0:
            print("✅ SUCCESS! Decoder output:")
            print()
            print(result.stdout)
            if result.stderr:
                print("Warnings/Info:")
                print(result.stderr)
        else:
            print("❌ Decoder returned error:")
            print(result.stderr)
            print("Stdout:")
            print(result.stdout)
            return 1
    except subprocess.TimeoutExpired:
        print("❌ Request timed out")
        return 1
    except Exception as e:
        print(f"❌ Error running decoder: {e}")
        return 1
    finally:
        # Cleanup
        if temp_payload.exists():
            temp_payload.unlink()
            print(f"\n✅ Cleaned up {temp_payload}")
    
    return 0


if __name__ == "__main__":
    sys.exit(test_nest_with_url())

