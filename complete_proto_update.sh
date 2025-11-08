#!/bin/bash
# Complete Proto Update Script - Updates all proto files to homebridge-nest feature parity

set -e

echo "=================================================================================="
echo "COMPLETE PROTO FILE UPDATE FOR HOMEBRIDGE-NEST FEATURE PARITY"
echo "=================================================================================="
echo ""

# Configuration
PROTO_ROOT="proto"
UPDATED_ROOT="proto/updated"
CAPTURES_DIR="captures"

# Step 1: Generate updated proto files
echo "Step 1: Generating updated proto files from captures..."
echo "--------------------------------------------------------"
python update_all_proto_files.py \
    --captures-dir "$CAPTURES_DIR" \
    --proto-root "$PROTO_ROOT" \
    --output-dir "$UPDATED_ROOT"

echo ""

# Step 2: Merge with existing proto files
echo "Step 2: Merging with existing proto files..."
echo "--------------------------------------------------------"

# Copy existing proto files to updated directory structure
if [ -d "$PROTO_ROOT" ]; then
    echo "Copying existing proto files..."
    find "$PROTO_ROOT" -name "*.proto" -not -path "*/updated/*" -not -path "*/autogen/*" | while read proto_file; do
        rel_path="${proto_file#$PROTO_ROOT/}"
        dest_path="$UPDATED_ROOT/$rel_path"
        dest_dir=$(dirname "$dest_path")
        mkdir -p "$dest_dir"
        
        # Only copy if updated version doesn't exist
        if [ ! -f "$dest_path" ]; then
            cp "$proto_file" "$dest_path"
            echo "  Copied: $rel_path"
        else
            echo "  Skipped (updated version exists): $rel_path"
        fi
    done
fi

echo ""

# Step 3: Compile proto files
echo "Step 3: Compiling proto files with protoc..."
echo "--------------------------------------------------------"

if command -v protoc &> /dev/null; then
    echo "Found protoc: $(protoc --version)"
    
    # Compile all proto files
    proto_count=0
    find "$UPDATED_ROOT" -name "*.proto" | while read proto_file; do
        proto_dir=$(dirname "$proto_file")
        proto_name=$(basename "$proto_file" .proto)
        
        echo "  Compiling: $proto_file"
        if protoc \
            --proto_path="$UPDATED_ROOT" \
            --proto_path="$PROTO_ROOT" \
            --python_out="$proto_dir" \
            "$proto_file" 2>&1; then
            proto_count=$((proto_count + 1))
            echo "    ✅ Generated: ${proto_dir}/${proto_name}_pb2.py"
        else
            echo "    ⚠️  Compilation had issues (may need imports)"
        fi
    done
    
    echo ""
    echo "  Compiled proto files (check output above for actual count)"
else
    echo "  ⚠️  protoc not found. Install with:"
    echo "     macOS: brew install protobuf"
    echo "     Linux: sudo apt-get install protobuf-compiler"
    echo ""
    echo "  Proto files are ready to compile when protoc is available."
fi

echo ""

# Step 4: Summary
echo "Step 4: Summary"
echo "--------------------------------------------------------"
echo ""
echo "✅ Updated proto files location: $UPDATED_ROOT"
echo ""
echo "Generated files:"
find "$UPDATED_ROOT" -name "*.proto" | wc -l | xargs echo "  Proto files:"
find "$UPDATED_ROOT" -name "*_pb2.py" 2>/dev/null | wc -l | xargs echo "  Python bindings:"
echo ""
echo "Next steps:"
echo "  1. Review proto files in: $UPDATED_ROOT"
echo "  2. Compare with existing files in: $PROTO_ROOT"
echo "  3. Merge changes as needed"
echo "  4. Update your integration to use the new proto files"
echo ""
echo "To use in your code:"
echo "  from proto.updated.nest.trait import user_pb2"
echo "  from proto.updated.weave.trait.security import boltlock_pb2"
echo ""
echo "=================================================================================="
echo "UPDATE COMPLETE"
echo "=================================================================================="

