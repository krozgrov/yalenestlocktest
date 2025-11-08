#!/usr/bin/env python3
"""
Fix import paths in proto files to use relative imports.
"""

import re
from pathlib import Path

HA_PROTO_DIR = Path("../ha-nest-yale-integration/custom_components/nest_yale_lock/proto")

# Import path mappings: (old_pattern, new_pattern)
IMPORT_FIXES = [
    (r'import "proto/', r'import "'),
    (r'import "google/protobuf/', r'import "zzzgoogle/protobuf/'),
]


def fix_proto_imports(proto_file: Path):
    """Fix import paths in a proto file."""
    try:
        with open(proto_file, 'r') as f:
            content = f.read()
        
        original = content
        
        # Apply fixes
        for old_pattern, new_pattern in IMPORT_FIXES:
            content = re.sub(old_pattern, new_pattern, content)
        
        if content != original:
            with open(proto_file, 'w') as f:
                f.write(content)
            return True
        return False
    except Exception as e:
        print(f"Error fixing {proto_file}: {e}")
        return False


def main():
    """Fix all proto files."""
    if not HA_PROTO_DIR.exists():
        print(f"Error: {HA_PROTO_DIR} does not exist")
        return 1
    
    proto_files = list(HA_PROTO_DIR.rglob("*.proto"))
    
    print(f"Fixing imports in {len(proto_files)} proto file(s)...")
    
    fixed = 0
    for proto_file in sorted(proto_files):
        if fix_proto_imports(proto_file):
            print(f"✅ Fixed: {proto_file.relative_to(HA_PROTO_DIR)}")
            fixed += 1
    
    print(f"\n✅ Fixed {fixed} proto file(s)")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())

