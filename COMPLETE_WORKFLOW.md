# Complete Workflow: From Hex Message to Updated Proto Files

This is a step-by-step guide showing how to decode a hex message and use it to generate/update proto files.

## Quick Example: Decode Your Hex Message

You already have a hex message from your integration logs. Here's how to use it:

```bash
# 1. Decode the hex message to see what's in it
python decode_hex_simple.py "0a8c0c1a8601..."

# Output shows:
# ✅ Structure ID: 018C86E39308F29F
# ✅ User ID: 015EADBA454C1770
# ✅ Device ID: DEVICE_00177A0000060303
```

## Full Workflow: Generate Proto Files from Captures

### Step 1: Capture Messages (if you haven't already)

```bash
python reverse_engineering.py \
  --traits "nest.trait.user.UserInfoTrait" \
           "nest.trait.structure.StructureInfoTrait" \
           "weave.trait.security.BoltLockTrait" \
  --output-dir captures \
  --limit 5
```

This creates `captures/20251013_.../` with:
- `*.raw.bin` - Raw protobuf bytes
- `*.typedef.json` - Field mappings (needed for proto generation)
- `*.blackbox.json` - Decoded data
- `*.pseudo.proto` - Preview of generated proto

### Step 2: Generate Proto Files

Use the existing tool:

```bash
python tools/generate_proto.py captures/20251013_.../ \
  --message-name StreamBodyMessage \
  --proto-root proto/autogen
```

This:
1. Merges all `*.typedef.json` files
2. Generates `proto/autogen/streambodymessage.proto`
3. Compiles it to `proto/autogen/nest/observe/streambodymessage_pb2.py`

### Step 3: Review the Generated Proto

```bash
cat proto/autogen/streambodymessage.proto
```

You'll see something like:
```protobuf
syntax = "proto3";
package nest.observe;

message StreamBodyMessage {
  repeated Field1Message field_1 = 1;
  
  message Field1Message {
    bytes field_1 = 1;
    string field_2 = 2;
    // ... more fields
  }
}
```

### Step 4: Improve Field Names (Optional)

Edit the proto file to add meaningful names:

```protobuf
message StreamBodyMessage {
  repeated GetOpMessage messages = 1;  // Changed from field_1
  
  message GetOpMessage {
    string object_id = 1;      // Changed from field_1
    string object_key = 2;     // Changed from field_2
    // ...
  }
}
```

### Step 5: Recompile

```bash
protoc --proto_path=proto/autogen \
       --python_out=proto/autogen \
       proto/autogen/streambodymessage.proto
```

### Step 6: Use in Your Code

```python
from proto.autogen.nest.observe import streambodymessage_pb2

# Decode a message
with open("captures/.../00001.raw.bin", "rb") as f:
    msg = streambodymessage_pb2.StreamBodyMessage()
    msg.ParseFromString(f.read())
    
    # Now you can access fields by name!
    for get_op in msg.messages:
        print(f"Object ID: {get_op.object_id}")
```

## Updating Existing Proto Files

If you want to update an existing proto file (like `proto/nest/rpc.proto`):

### Option A: Manual Merge

1. Generate new proto from captures
2. Compare with existing proto
3. Manually add missing fields
4. Recompile

### Option B: Generate New Message Types

Generate proto for specific message types:

```bash
# Generate proto for StreamBody
python tools/generate_proto.py captures/LATEST/ \
  --message-name StreamBody \
  --proto-root proto/nest \
  --python-out proto/nest
```

## Generating ObserveTraits.bin

To generate the binary request file:

```python
from proto.nestlabs.gateway import v2_pb2

req = v2_pb2.ObserveRequest(version=2, subscribe=True)

traits = [
    "nest.trait.user.UserInfoTrait",
    "nest.trait.structure.StructureInfoTrait",
    "weave.trait.security.BoltLockTrait",
    "weave.trait.security.BoltLockSettingsTrait",
    "weave.trait.security.BoltLockCapabilitiesTrait",
    "weave.trait.security.PincodeInputTrait",
    "weave.trait.security.TamperTrait",
]

for trait in traits:
    filt = req.filter.add()
    filt.trait_type = trait

# Save to binary file
with open("proto/ObserveTraits.bin", "wb") as f:
    f.write(req.SerializeToString())
```

## Complete Example Script

```bash
#!/bin/bash
# complete_workflow.sh

# 1. Capture messages
echo "Step 1: Capturing messages..."
python reverse_engineering.py \
  --traits "weave.trait.security.BoltLockTrait" \
  --output-dir captures \
  --limit 3

# 2. Find latest capture
LATEST=$(ls -td captures/*/ | head -1)
echo "Using capture: $LATEST"

# 3. Extract IDs
echo "Step 2: Extracting IDs..."
python extract_ids.py "$LATEST"

# 4. Generate proto
echo "Step 3: Generating proto files..."
python tools/generate_proto.py "$LATEST" \
  --message-name StreamBodyMessage \
  --proto-root proto/autogen

# 5. Show results
echo "Step 4: Generated files:"
ls -la proto/autogen/*.proto
ls -la proto/autogen/nest/observe/*_pb2.py 2>/dev/null || echo "Run protoc to generate pb2 files"

echo "Done! Review proto/autogen/streambodymessage.proto"
```

## Troubleshooting

### protoc not found
```bash
# macOS
brew install protobuf

# Linux
sudo apt-get install protobuf-compiler

# Verify
protoc --version
```

### Import errors
Make sure proto directory is in Python path:
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path("proto").resolve()))
```

### Field type errors
If protoc complains about field types:
1. Check the typedef.json to see actual types
2. Manually fix the proto file
3. Recompile

## Next Steps

1. **Capture more messages** with different traits to get complete typedefs
2. **Merge multiple captures** to build comprehensive proto definitions  
3. **Manually refine** field names based on your understanding
4. **Update your integration** to use the improved proto files
5. **Test** with real messages to verify decoding works

## Files Created

- `GENERATE_PROTO_GUIDE.md` - Detailed guide
- `update_proto_from_captures.py` - Enhanced generation tool
- `decode_hex_simple.py` - Decode hex messages
- `COMPLETE_WORKFLOW.md` - This file

## Quick Reference

| Command | Purpose |
|---------|---------|
| `python reverse_engineering.py ...` | Capture messages |
| `python tools/generate_proto.py ...` | Generate proto files |
| `python decode_hex_simple.py "hex"` | Decode hex message |
| `python extract_ids.py captures/.../` | Extract IDs from captures |
| `protoc --proto_path=... --python_out=...` | Compile proto to pb2 |

