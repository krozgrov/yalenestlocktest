#!/usr/bin/env python3
"""
Analyze the actual stream format to understand why DecodeErrors occur.

This captures raw chunks and analyzes them to see if they're:
1. Direct StreamBody messages (no varint prefix)
2. Varint-prefixed StreamBody messages
3. Something else entirely
"""

import asyncio
import sys
from pathlib import Path
from dotenv import load_dotenv
import requests

from auth import GetSessionWithAuth
from proto.nestlabs.gateway import v2_pb2
from proto.nest import rpc_pb2
from const import (
    USER_AGENT_STRING,
    URL_PROTOBUF,
    ENDPOINT_OBSERVE,
    PRODUCTION_HOSTNAME,
    API_TIMEOUT_SECONDS,
)


def decode_varint(buffer, pos):
    """Decode varint from buffer starting at pos."""
    value = 0
    shift = 0
    start = pos
    max_bytes = 10
    while pos < len(buffer) and shift < 64:
        byte = buffer[pos]
        value |= (byte & 0x7F) << shift
        pos += 1
        shift += 7
        if not (byte & 0x80):
            return value, pos
        if pos - start >= max_bytes:
            return None, pos
    return None, pos


def test_parse_as_streambody(data):
    """Test if data can be parsed as StreamBody."""
    try:
        stream_body = rpc_pb2.StreamBody()
        stream_body.ParseFromString(data)
        return True, stream_body
    except Exception as e:
        return False, str(e)


async def main():
    load_dotenv()
    
    print("="*80)
    print("ANALYZING STREAM FORMAT")
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
    print("Analyzing first 10 chunks...")
    print()
    
    chunk_count = 0
    total_bytes = 0
    
    try:
        for chunk in response.iter_content(chunk_size=None):
            if not chunk or not chunk.strip():
                continue
            
            chunk_count += 1
            total_bytes += len(chunk)
            
            print(f"Chunk {chunk_count}: {len(chunk)} bytes")
            print(f"  First 20 bytes (hex): {chunk[:20].hex()}")
            
            # Test 1: Parse entire chunk as StreamBody
            can_parse, result = test_parse_as_streambody(chunk)
            if can_parse:
                print(f"  ✅ Parses as StreamBody directly!")
                stream_body = result
                print(f"     Messages: {len(stream_body.message)}")
                if stream_body.message:
                    msg = stream_body.message[0]
                    print(f"     Get ops: {len(msg.get)}")
                    print(f"     Set ops: {len(msg.set)}")
            else:
                print(f"  ❌ Does NOT parse as StreamBody: {result[:100]}")
            
            # Test 2: Try varint extraction
            length, offset = decode_varint(chunk, 0)
            if length is not None and offset < len(chunk):
                extracted = chunk[offset:offset + length] if offset + length <= len(chunk) else chunk[offset:]
                print(f"  Varint: length={length}, offset={offset}, extracted={len(extracted)} bytes")
                
                can_parse_extracted, result_extracted = test_parse_as_streambody(extracted)
                if can_parse_extracted:
                    print(f"  ✅ Extracted message parses as StreamBody!")
                    stream_body = result_extracted
                    print(f"     Messages: {len(stream_body.message)}")
                else:
                    print(f"  ❌ Extracted message does NOT parse: {result_extracted[:100]}")
            
            print()
            
            if chunk_count >= 10:
                break
    
    except KeyboardInterrupt:
        print("\n⚠️  Interrupted")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        response.close()
    
    print(f"\n{'='*80}")
    print(f"Summary: Analyzed {chunk_count} chunks, {total_bytes} total bytes")
    print("="*80)
    
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

