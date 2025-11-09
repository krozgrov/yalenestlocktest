#!/usr/bin/env python3
"""
Final test using enhanced handler to decode all traits.
"""

import sys
import asyncio
from pathlib import Path

from enhanced_protobuf_handler import EnhancedProtobufHandler


async def test_file(capture_file: Path):
    """Test a single capture file."""
    print(f"\n{'='*80}")
    print(f"Testing: {capture_file.name}")
    print(f"{'='*80}\n")
    
    handler = EnhancedProtobufHandler()
    
    try:
        with open(capture_file, "rb") as f:
            raw_data = f.read()
        
        # Process message
        result = await handler._process_message(raw_data)
        
        print("✅ Message processed successfully\n")
        
        # Show lock data
        if result.get("yale"):
            print("Lock Data:")
            for device_id, device_data in result["yale"].items():
                print(f"  Device: {device_id}")
                for key, value in device_data.items():
                    print(f"    {key}: {value}")
            print()
        
        if result.get("user_id"):
            print(f"User ID: {result['user_id']}")
        if result.get("structure_id"):
            print(f"Structure ID: {result['structure_id']}")
        print()
        
        # Show all traits
        all_traits = result.get("all_traits", {})
        if all_traits:
            print(f"All Traits ({len(all_traits)}):\n")
            
            decoded_count = 0
            for trait_key, trait_info in sorted(all_traits.items()):
                type_url = trait_info["type_url"]
                obj_id = trait_info["object_id"]
                
                print(f"  {type_url}")
                print(f"    Object ID: {obj_id}")
                
                if trait_info.get("decoded"):
                    decoded_count += 1
                    print(f"    ✅ Decoded")
                    for key, value in trait_info.get("data", {}).items():
                        if value is not None:
                            print(f"       {key}: {value}")
                elif "error" in trait_info:
                    print(f"    ❌ Error: {trait_info['error']}")
                else:
                    print(f"    ⚠️  No decoder")
                print()
            
            print(f"Summary: {decoded_count}/{len(all_traits)} traits decoded successfully")
        else:
            print("⚠️  No traits extracted")
    
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Test all trait decoding")
    parser.add_argument("--capture-dir", type=Path, help="Capture directory")
    
    args = parser.parse_args()
    
    if args.capture_dir:
        capture_dir = args.capture_dir
    else:
        captures_dir = Path("captures")
        capture_dirs = sorted([d for d in captures_dir.iterdir() if d.is_dir()],
                            key=lambda x: x.stat().st_mtime, reverse=True)
        if not capture_dirs:
            print("Error: No captures found")
            return 1
        capture_dir = capture_dirs[0]
    
    print("="*80)
    print("COMPREHENSIVE TRAIT DECODING TEST")
    print("="*80)
    print(f"Capture: {capture_dir.name}\n")
    
    raw_files = sorted(capture_dir.glob("*.raw.bin"))
    if not raw_files:
        print("⚠️  No raw.bin files found")
        return 1
    
    for raw_file in raw_files:
        asyncio.run(test_file(raw_file))
    
    return 0


if __name__ == "__main__":
    sys.exit(main())

