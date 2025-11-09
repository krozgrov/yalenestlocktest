"""
Comprehensive test script to verify decoding of ALL traits for:
- Locks (BoltLock traits)
- Thermostats (HVAC traits)
- Smoke Alarms (Detector traits)
- Sensors (Temperature, Humidity)
"""

import asyncio
import json
import sys
import logging
import time
from dotenv import load_dotenv
import requests
from pathlib import Path
from collections import defaultdict

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

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
_LOGGER = logging.getLogger(__name__)
logging.getLogger('protobuf_handler_enhanced').setLevel(logging.INFO)

# Define all traits we want to test
ALL_TRAITS = {
    # Lock traits
    "weave.trait.security.BoltLockTrait",
    "weave.trait.security.BoltLockSettingsTrait",
    "weave.trait.security.BoltLockCapabilitiesTrait",
    "weave.trait.security.PincodeInputTrait",
    "weave.trait.security.TamperTrait",
    # HVAC traits (thermostats)
    "nest.trait.hvac.TargetTemperatureSettingsTrait",
    "nest.trait.hvac.HvacControlTrait",
    "nest.trait.hvac.EcoModeStateTrait",
    "nest.trait.hvac.EcoModeSettingsTrait",
    "nest.trait.hvac.DisplaySettingsTrait",
    "nest.trait.hvac.FanControlSettingsTrait",
    "nest.trait.hvac.FanControlTrait",
    "nest.trait.hvac.BackplateInfoTrait",
    "nest.trait.hvac.HvacEquipmentCapabilitiesTrait",
    # Detector traits (smoke alarms)
    "nest.trait.detector.OpenCloseTrait",
    "nest.trait.detector.AmbientMotionTrait",
    "nest.trait.detector.AmbientMotionTimingSettingsTrait",
    "nest.trait.detector.AmbientMotionSettingsTrait",
    # Sensor traits
    "nest.trait.sensor.TemperatureTrait",
    "nest.trait.sensor.HumidityTrait",
    # Common traits
    "weave.trait.description.DeviceIdentityTrait",
    "weave.trait.power.BatteryPowerSourceTrait",
}

async def main():
    load_dotenv()

    print("="*80)
    print("COMPREHENSIVE TRAIT DECODING TEST")
    print("="*80)
    print("\nThis test verifies decoding of ALL traits for:")
    print("  - Locks (BoltLock traits)")
    print("  - Thermostats (HVAC traits)")
    print("  - Smoke Alarms (Detector traits)")
    print("  - Sensors (Temperature, Humidity)")
    print(f"\nTotal traits to test: {len(ALL_TRAITS)}\n")

    # Authenticate
    session, access_token, user_id, transport_url = GetSessionWithAuth()
    print("✅ Authenticated")

    # Build request with all traits
    req = v2_pb2.ObserveRequest(version=2, subscribe=True)
    for trait_name in ALL_TRAITS:
        filt = req.filter.add()
        filt.trait_type = trait_name
    payload = req.SerializeToString()

    headers = {
        "Authorization": f"Basic {access_token}",
        "Content-Type": "application/x-protobuf",
        "User-Agent": USER_AGENT_STRING,
        "X-Accept-Response-Streaming": "true",
        "Accept": "application/x-protobuf",
        "X-Accept-Content-Transfer-Encoding": "binary",
        "Accept-Encoding": "gzip, deflate, br",
        "referer": "https://home.nest.com/",
        "origin": "https://home.nest.com",
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
                timeout=(API_TIMEOUT_SECONDS, 60),  # Increased read timeout to 60 seconds
            )
            response.raise_for_status()
            print(f"✅ Connected to {base_url}")
            break
        except Exception as e:
            print(f"⚠️  Failed to connect to {base_url}: {e}")
            continue

    if not response:
        print("❌ Connection failed to all endpoints")
        return 1

    # Process chunks - collect all traits by device
    handler = EnhancedProtobufHandler()
    message_count = 0
    devices_traits = defaultdict(dict)  # device_id -> {trait_name: trait_data}
    device_info = {}  # device_id -> DeviceIdentityTrait data
    
    print(f"\nProcessing messages...\n")

    try:
        start_time = time.time()
        max_wait_time = 30  # Wait up to 30 seconds for messages
        
        for chunk in response.iter_content(chunk_size=None):
            if not chunk or not chunk.strip():
                continue

            # Try parsing directly as StreamBody first (like the handler's stream method does)
            locks_data = None
            try:
                from proto.nest import rpc_pb2 as rpc
                test_stream = rpc.StreamBody()
                test_stream.ParseFromString(chunk)
                # Success! This chunk is a complete StreamBody
                locks_data = await handler._process_message(chunk)
            except:
                # Not a direct StreamBody, use handler's varint extraction
                # Add chunk to handler's buffer and process complete messages
                if handler.pending_length is None:
                    handler.pending_length, offset = handler._decode_varint(chunk, 0)
                    if handler.pending_length is None or offset >= len(chunk):
                        continue
                    handler.buffer.extend(chunk[offset:])
                else:
                    handler.buffer.extend(chunk)
                
                # Process complete messages from buffer
                while handler.pending_length and len(handler.buffer) >= handler.pending_length:
                    message = bytes(handler.buffer[:handler.pending_length])
                    handler.buffer = handler.buffer[handler.pending_length:]
                    locks_data = await handler._process_message(message)
                    handler.pending_length = None if len(handler.buffer) < 5 else handler._decode_varint(handler.buffer, 0)[0]
                    
                    # Process this decoded message
                    if locks_data:
                        break  # Process this message, then continue to next chunk
                
                # If no complete message was extracted, continue to next chunk
                if not locks_data:
                    continue

            # Check for traits
            if not locks_data:
                continue
                
            all_traits = locks_data.get("all_traits", {})
            if all_traits:
                for trait_key, trait_info in all_traits.items():
                    obj_id = trait_info.get("object_id", "")
                    type_url = trait_info.get("type_url", "")
                    
                    if not obj_id or not type_url:
                        continue
                    
                    # Extract trait name from type_url
                    trait_name = type_url.split(".")[-1]
                    
                    # Store DeviceIdentityTrait separately for device info
                    if "DeviceIdentityTrait" in type_url and trait_info.get("decoded"):
                        device_info[obj_id] = trait_info.get("data", {})
                    
                    # Store trait data
                    if trait_info.get("decoded"):
                        devices_traits[obj_id][trait_name] = {
                            "type_url": type_url,
                            "data": trait_info.get("data", {}),
                        }
                        message_count += 1
                        
                        # Print when we find a new trait
                        device_name = device_info.get(obj_id, {}).get("model") or device_info.get(obj_id, {}).get("serial_number") or obj_id
                        print(f"📦 Found {trait_name} for {device_name} ({obj_id})")
                        if trait_info.get("data"):
                            for key, value in trait_info.get("data", {}).items():
                                if value is not None:
                                    print(f"   {key}: {value}")
                        print()
                
                # Reset timer when we get messages
                start_time = time.time()

            # Stop after processing enough messages or if we've waited long enough
            elapsed = time.time() - start_time
            if message_count > 100 or (message_count > 0 and elapsed > max_wait_time):
                print(f"\n⏱️  Stopping after {message_count} messages (waited {elapsed:.1f}s)")
                break

    except requests.exceptions.ConnectionError as e:
        _LOGGER.warning(f"Connection error (this is normal if we got some data): {e}")
        # Continue to show summary if we got any data
    except requests.exceptions.ReadTimeout as e:
        _LOGGER.warning(f"Read timeout (this is normal after receiving initial data): {e}")
        # Continue to show summary if we got any data
    except Exception as e:
        _LOGGER.error(f"An unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if response:
            response.close()

    # Summary by device type
    print("="*80)
    print("SUMMARY BY DEVICE TYPE")
    print("="*80)
    
    # Categorize devices
    locks = []
    thermostats = []
    smoke_alarms = []
    sensors = []
    other = []
    
    for device_id, traits in devices_traits.items():
        device_name = device_info.get(device_id, {}).get("model") or device_info.get(device_id, {}).get("serial_number") or device_id
        
        # Determine device type based on traits
        if "BoltLockTrait" in traits:
            locks.append((device_id, device_name, traits))
        elif "HvacControlTrait" in traits or "TargetTemperatureSettingsTrait" in traits:
            thermostats.append((device_id, device_name, traits))
        elif "OpenCloseTrait" in traits or "AmbientMotionTrait" in traits:
            smoke_alarms.append((device_id, device_name, traits))
        elif "TemperatureTrait" in traits or "HumidityTrait" in traits:
            sensors.append((device_id, device_name, traits))
        else:
            other.append((device_id, device_name, traits))
    
    # Print summary
    print(f"\n🔒 LOCKS ({len(locks)}):")
    for device_id, device_name, traits in locks:
        print(f"   {device_name} ({device_id})")
        print(f"      Traits: {', '.join(sorted(traits.keys()))}")
    
    print(f"\n🌡️  THERMOSTATS ({len(thermostats)}):")
    for device_id, device_name, traits in thermostats:
        print(f"   {device_name} ({device_id})")
        print(f"      Traits: {', '.join(sorted(traits.keys()))}")
    
    print(f"\n🚨 SMOKE ALARMS ({len(smoke_alarms)}):")
    for device_id, device_name, traits in smoke_alarms:
        print(f"   {device_name} ({device_id})")
        print(f"      Traits: {', '.join(sorted(traits.keys()))}")
    
    print(f"\n📊 SENSORS ({len(sensors)}):")
    for device_id, device_name, traits in sensors:
        print(f"   {device_name} ({device_id})")
        print(f"      Traits: {', '.join(sorted(traits.keys()))}")
    
    if other:
        print(f"\n❓ OTHER DEVICES ({len(other)}):")
        for device_id, device_name, traits in other:
            print(f"   {device_name} ({device_id})")
            print(f"      Traits: {', '.join(sorted(traits.keys()))}")
    
    # Trait coverage summary
    print("\n" + "="*80)
    print("TRAIT COVERAGE SUMMARY")
    print("="*80)
    
    all_found_traits = set()
    for traits_dict in devices_traits.values():
        for trait_name in traits_dict.keys():
            all_found_traits.add(trait_name)
    
    print(f"\nTotal unique traits decoded: {len(all_found_traits)}")
    print(f"Expected traits: {len(ALL_TRAITS)}")
    
    print("\n✅ Traits successfully decoded:")
    for trait in sorted(all_found_traits):
        print(f"   - {trait}")
    
    missing_traits = set()
    for trait_url in ALL_TRAITS:
        trait_name = trait_url.split(".")[-1]
        if trait_name not in all_found_traits:
            missing_traits.add(trait_name)
    
    if missing_traits:
        print("\n⚠️  Traits not found in messages (may not be present in your devices):")
        for trait in sorted(missing_traits):
            print(f"   - {trait}")
    else:
        print("\n✅ All expected traits were found!")
    
    print(f"\nTotal messages processed: {message_count}")
    print(f"Total devices found: {len(devices_traits)}")
    
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

