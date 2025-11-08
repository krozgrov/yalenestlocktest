#!/bin/bash
# Automated workflow: Capture messages and generate proto files

set -e  # Exit on error

echo "=================================================================================="
echo "AUTOMATED PROTO GENERATION WORKFLOW"
echo "=================================================================================="
echo ""

# Configuration
TRAITS=(
    "nest.trait.user.UserInfoTrait"
    "nest.trait.structure.StructureInfoTrait"
    "weave.trait.security.BoltLockTrait"
    "weave.trait.security.BoltLockSettingsTrait"
    "weave.trait.security.BoltLockCapabilitiesTrait"
    "weave.trait.security.PincodeInputTrait"
    "weave.trait.security.TamperTrait"
)
CAPTURE_LIMIT=3
OUTPUT_DIR="captures"
PROTO_ROOT="proto/autogen"
MESSAGE_NAME="StreamBodyMessage"

# Step 1: Capture messages
echo "Step 1: Capturing protobuf messages..."
echo "----------------------------------------"
python reverse_engineering.py \
    --traits "${TRAITS[@]}" \
    --output-dir "$OUTPUT_DIR" \
    --limit "$CAPTURE_LIMIT" \
    --no-parsed 2>&1 | grep -E "(Stored|chunk|Attempting|Observe)" || true

# Find the latest capture directory
LATEST_CAPTURE=$(ls -td "$OUTPUT_DIR"/*/ 2>/dev/null | head -1)

if [ -z "$LATEST_CAPTURE" ]; then
    echo "❌ Error: No capture directory found!"
    exit 1
fi

echo ""
echo "✅ Capture complete: $LATEST_CAPTURE"
echo ""

# Step 2: Extract IDs
echo "Step 2: Extracting IDs from captured messages..."
echo "----------------------------------------"
python extract_ids.py "$LATEST_CAPTURE" 2>&1 | tail -20 || echo "Note: extract_ids.py may have issues, continuing..."

echo ""

# Step 3: Generate proto files
echo "Step 3: Generating proto files from typedefs..."
echo "----------------------------------------"

# Check if typedef files exist
TYPEDEF_COUNT=$(find "$LATEST_CAPTURE" -name "*.typedef.json" | wc -l | tr -d ' ')

if [ "$TYPEDEF_COUNT" -eq 0 ]; then
    echo "⚠️  Warning: No typedef.json files found. Trying to generate them..."
    echo "   (This requires blackboxprotobuf to be installed)"
    
    # Try to generate typedefs if we have blackbox JSON
    if [ -f "$LATEST_CAPTURE/00001.blackbox.json" ]; then
        echo "   Found blackbox JSON files, but typedefs are missing."
        echo "   You may need to re-run reverse_engineering.py with blackbox enabled."
    fi
else
    echo "   Found $TYPEDEF_COUNT typedef file(s)"
    
    # Try to use the existing tool
    if [ -f "tools/generate_proto.py" ]; then
        echo "   Using tools/generate_proto.py..."
        python tools/generate_proto.py "$LATEST_CAPTURE" \
            --message-name "$MESSAGE_NAME" \
            --proto-root "$PROTO_ROOT" \
            --skip-protoc 2>&1 || {
            echo "   ⚠️  tools/generate_proto.py failed, trying alternative..."
            python update_proto_from_captures.py "$LATEST_CAPTURE" \
                --message-name "$MESSAGE_NAME" \
                --proto-root "$PROTO_ROOT" \
                --skip-protoc 2>&1 || echo "   ❌ Proto generation failed"
        }
    else
        echo "   Using update_proto_from_captures.py..."
        python update_proto_from_captures.py "$LATEST_CAPTURE" \
            --message-name "$MESSAGE_NAME" \
            --proto-root "$PROTO_ROOT" \
            --skip-protoc 2>&1 || echo "   ❌ Proto generation failed"
    fi
fi

echo ""

# Step 4: Show results
echo "Step 4: Results"
echo "----------------------------------------"

# Check for generated proto files (convert to lowercase)
MESSAGE_NAME_LOWER=$(echo "$MESSAGE_NAME" | tr '[:upper:]' '[:lower:]')
PROTO_FILE="$PROTO_ROOT/${MESSAGE_NAME_LOWER}.proto"
if [ -f "$PROTO_FILE" ]; then
    echo "✅ Generated proto file: $PROTO_FILE"
    echo ""
    echo "   First 30 lines:"
    head -30 "$PROTO_FILE" | sed 's/^/   /'
    echo ""
    echo "   File size: $(wc -l < "$PROTO_FILE") lines"
else
    echo "⚠️  Proto file not found: $PROTO_FILE"
fi

# Check for pb2 files
PB2_DIR="$PROTO_ROOT/nest/observe"
if [ -d "$PB2_DIR" ] && [ -n "$(find "$PB2_DIR" -name "*_pb2.py" 2>/dev/null)" ]; then
    echo ""
    echo "✅ Generated pb2 files in: $PB2_DIR"
    find "$PB2_DIR" -name "*_pb2.py" | sed 's/^/   /'
else
    echo ""
    echo "ℹ️  To generate pb2 files, run:"
    echo "   protoc --proto_path=$PROTO_ROOT --python_out=$PROTO_ROOT $PROTO_FILE"
fi

echo ""
echo "=================================================================================="
echo "WORKFLOW COMPLETE"
echo "=================================================================================="
echo ""
echo "Next steps:"
echo "  1. Review: $PROTO_FILE"
echo "  2. Improve field names manually if needed"
echo "  3. Compile: protoc --proto_path=$PROTO_ROOT --python_out=$PROTO_ROOT $PROTO_FILE"
echo "  4. Use in your code: from proto.autogen.nest.observe import ${MESSAGE_NAME_LOWER}_pb2"
echo ""

