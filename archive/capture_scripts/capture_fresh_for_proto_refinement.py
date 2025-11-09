#!/usr/bin/env python3
"""
Capture fresh Observe responses for proto refinement.

This script uses reverse_engineering.py's approach but avoids the proto pool import issue.
It captures raw responses and uses blackboxprotobuf to analyze structure.
"""

import sys
import json
import asyncio
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv
import os
import requests

# Import auth and const without proto_utils
from auth import GetSessionWithAuth
from const import (
    ENDPOINT_OBSERVE,
    PRODUCTION_HOSTNAME,
    URL_PROTOBUF,
    API_TIMEOUT_SECONDS,
    USER_AGENT_STRING,
)

try:
    import blackboxprotobuf as bbp
    BLACKBOX_AVAILABLE = True
except ImportError:
    BLACKBOX_AVAILABLE = False
    print("Error: blackboxprotobuf required. Install with: pip install blackboxprotobuf")
    sys.exit(1)

# Import proto generation utilities from reverse_engineering
from reverse_engineering import (
    typedef_to_pseudo_proto,
    prepare_run_dir,
    utc_timestamp,
    resolve_transport_override,
    _normalize_base,
)

# Import v2_pb2 for ObserveRequest (this should work)
sys.path.insert(0, str(Path(__file__).parent / "proto"))
from proto.nestlabs.gateway import v2_pb2


def send_observe_request(session, access_token, traits, base_url):
    """Send Observe request without using proto_utils."""
    req = v2_pb2.ObserveRequest(version=2, subscribe=True)
    for trait_name in traits:
        filt = req.filter.add()
        filt.trait_type = trait_name
    payload = req.SerializeToString()
    
    headers = {
        "Accept-Encoding": "gzip, deflate, br, zstd",
        "Content-Type": "application/x-protobuf",
        "User-Agent": USER_AGENT_STRING,
        "X-Accept-Response-Streaming": "true",
        "Accept": "application/x-protobuf",
        "referer": "https://home.nest.com/",
        "origin": "https://home.nest.com",
        "X-Accept-Content-Transfer-Encoding": "binary",
        "Authorization": "Basic " + access_token,
    }
    
    full_url = f"{_normalize_base(base_url)}{ENDPOINT_OBSERVE}"
    response = session.post(
        full_url,
        headers=headers,
        data=payload,
        stream=True,
        timeout=(API_TIMEOUT_SECONDS, API_TIMEOUT_SECONDS),
    )
    response.raise_for_status()
    return response


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Capture fresh Observe responses for proto refinement"
    )
    parser.add_argument(
        "--traits",
        nargs="+",
        default=[
            "nest.trait.user.UserInfoTrait",
            "nest.trait.structure.StructureInfoTrait",
            "weave.trait.security.BoltLockTrait",
            "weave.trait.security.BoltLockSettingsTrait",
            "weave.trait.security.BoltLockCapabilitiesTrait",
            "weave.trait.security.PincodeInputTrait",
            "weave.trait.security.TamperTrait",
            "weave.trait.description.DeviceIdentityTrait",
            "weave.trait.power.BatteryPowerSourceTrait",
        ],
        help="Traits to capture",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Number of messages to capture",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("captures"),
        help="Output directory",
    )
    
    args = parser.parse_args()
    
    load_dotenv()
    
    print("="*80)
    print("CAPTURING FRESH DATA FOR PROTO REFINEMENT")
    print("="*80)
    print()
    print(f"Traits: {', '.join(args.traits)}")
    print(f"Limit: {args.limit} messages")
    print()
    
    # Authenticate
    print("Authenticating...")
    session, access_token, _, transport_url = GetSessionWithAuth()
    print("✅ Authentication successful")
    print()
    
    # Determine transport URL
    default_base = URL_PROTOBUF.format(grpc_hostname=PRODUCTION_HOSTNAME["grpc_hostname"])
    base_candidates = []
    if transport_url:
        base_candidates.append(_normalize_base(transport_url))
    base_candidates.append(_normalize_base(default_base))
    
    # Send Observe request
    response = None
    for base in base_candidates:
        try:
            print(f"Sending Observe request to {base}...")
            response = send_observe_request(session, access_token, args.traits, base)
            print("✅ Observe stream connected")
            break
        except Exception as e:
            print(f"❌ Failed: {e}")
            continue
    
    if not response:
        print("❌ Failed to connect to Observe stream")
        return 1
    
    # Prepare output directory
    run_dir = prepare_run_dir(args.output_dir, args.traits)
    print(f"Output directory: {run_dir}")
    print()
    
    # Process messages
    chunk_count = 0
    manifest = []
    
    print("Capturing messages...")
    print()
    
    try:
        for chunk in response.iter_content(chunk_size=None):
            if not chunk or not chunk.strip():
                continue
            
            chunk_count += 1
            chunk_prefix = f"{chunk_count:05d}"
            
            # Save raw
            raw_path = run_dir / f"{chunk_prefix}.raw.bin"
            raw_path.write_bytes(chunk)
            
            entry = {
                "index": chunk_count,
                "timestamp": utc_timestamp(),
                "raw": raw_path.name,
            }
            
            # Decode with blackboxprotobuf
            try:
                message_json, typedef = bbp.protobuf_to_json(chunk)
                
                blackbox_path = run_dir / f"{chunk_prefix}.blackbox.json"
                blackbox_path.write_text(json.dumps(message_json, indent=2))
                
                typedef_path = run_dir / f"{chunk_prefix}.typedef.json"
                typedef_path.write_text(json.dumps(typedef, indent=2, sort_keys=True, default=str))
                
                pseudo_proto = typedef_to_pseudo_proto(typedef, "ObservedMessage")
                pseudo_path = run_dir / f"{chunk_prefix}.pseudo.proto"
                pseudo_path.write_text(pseudo_proto)
                
                entry["blackbox"] = {
                    "message": blackbox_path.name,
                    "typedef": typedef_path.name,
                    "pseudo_proto": pseudo_path.name,
                }
                
                print(f"✅ Message {chunk_count}: {len(chunk)} bytes")
                print(f"   Fields: {list(typedef.keys())}")
                
            except Exception as e:
                entry["blackbox_error"] = str(e)
                print(f"⚠️  Message {chunk_count}: blackbox decode failed: {e}")
            
            manifest.append(entry)
            
            if chunk_count >= args.limit:
                break
    
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted by user")
    finally:
        response.close()
        session.close()
    
    # Save manifest
    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    
    print()
    print("="*80)
    print("CAPTURE COMPLETE")
    print("="*80)
    print(f"Captured {chunk_count} message(s)")
    print(f"Location: {run_dir}")
    print()
    print("Next steps:")
    print("1. Review the pseudo.proto files to see the actual structure")
    print("2. Compare with proto/nest/rpc.proto")
    print("3. Update proto files to match API v2 structure")
    print("4. Regenerate pb2.py files")
    print("5. Test parsing")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

