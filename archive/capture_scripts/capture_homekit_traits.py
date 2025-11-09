#!/usr/bin/env python3
"""
Capture messages with HomeKit-relevant traits to extract:
- Serial numbers
- Battery information
- Firmware versions
- Device descriptions
- Power status
"""

import sys
from pathlib import Path

# Import reverse engineering tool
try:
    from reverse_engineering import capture_observe_stream
except ImportError:
    print("Error: reverse_engineering.py not found")
    sys.exit(1)


def main():
    # HomeKit-relevant traits to capture
    homekit_traits = [
        # Device identity (serial, model, firmware)
        "weave.trait.description.DeviceIdentityTrait",
        
        # Power/battery information
        "weave.trait.power.PowerTrait",
        
        # Device description
        "weave.trait.description.DescriptionTrait",
        
        # Lock traits (we already have these)
        "weave.trait.security.BoltLockTrait",
        "weave.trait.security.BoltLockSettingsTrait",
        "weave.trait.security.BoltLockCapabilitiesTrait",
        
        # Structure and user (for IDs)
        "nest.trait.structure.StructureInfoTrait",
        "nest.trait.user.UserInfoTrait",
    ]
    
    print("="*80)
    print("CAPTURING MESSAGES WITH HOMEKIT-RELEVANT TRAITS")
    print("="*80)
    print()
    print("Traits to capture:")
    for trait in homekit_traits:
        print(f"  - {trait}")
    print()
    
    output_dir = Path("captures")
    output_dir.mkdir(exist_ok=True)
    
    try:
        run_dir, chunk_count = capture_observe_stream(
            traits=homekit_traits,
            output_dir=output_dir,
            limit=5,
            capture_blackbox=True,
            capture_parsed=False,
            echo_blackbox=False,
            echo_parsed=False,
        )
        
        print()
        print("="*80)
        print("CAPTURE COMPLETE")
        print("="*80)
        print(f"Captured {chunk_count} message(s)")
        print(f"Location: {run_dir}")
        print()
        print("Next: Run extract_homekit_info.py to extract HomeKit data")
        
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

