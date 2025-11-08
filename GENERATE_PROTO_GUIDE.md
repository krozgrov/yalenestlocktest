# Guide: Generating Proto Files from Captured Messages

This guide shows you how to use captured protobuf messages to generate/update `.proto` files and compile them to `pb2.py` files.

## Overview

The workflow is:
1. **Capture messages** → Get raw protobuf bytes
2. **Decode with blackboxprotobuf** → Get typedefs (field mappings)
3. **Generate .proto files** → Convert typedefs to proto syntax
4. **Compile to pb2.py** → Use protoc to generate Python bindings

## Step-by-Step Process

### Step 1: Capture Messages

First, capture some protobuf messages:

```bash
python reverse_engineering.py \
  --traits "nest.trait.user.UserInfoTrait" \
           "nest.trait.structure.StructureInfoTrait" \
           "weave.trait.security.BoltLockTrait" \
  --output-dir captures \
  --limit 5
```

This creates a directory like `captures/20251013_201107_.../` with:
- `*.raw.bin` - Raw protobuf bytes
- `*.blackbox.json` - Decoded JSON
- `*.typedef.json` - Field mappings (what we need!)
- `*.pseudo.proto` - Generated proto (preview)

### Step 2: Generate Proto Files

Use the existing tool to generate proto files from typedefs:

```bash
python tools/generate_proto.py captures/20251013_201107_.../ \
  --message-name StreamBodyMessage \
  --proto-root proto/autogen
```

This will:
1. Merge all `*.typedef.json` files from the capture
2. Generate `proto/autogen/streambodymessage.proto`
3. Compile it to `proto/autogen/nest/observe/streambodymessage_pb2.py`

### Step 3: Use the Generated Files

The generated `pb2.py` files can now be imported:

```python
from proto.autogen.nest.observe import streambodymessage_pb2

# Use it to decode messages
message = streambodymessage_pb2.StreamBodyMessage()
message.ParseFromString(raw_bytes)
```

## Advanced: Updating Existing Proto Files

### Option A: Merge with Existing Proto

If you want to update an existing proto file (like `rpc.proto`), you can:

1. **Extract specific message types** from captures
2. **Manually merge** the new fields into existing proto files
3. **Recompile** with protoc

### Option B: Generate New Proto Files

Generate new proto files for specific message types:

```bash
# Generate proto for StreamBody messages
python tools/generate_proto.py captures/LATEST/ \
  --message-name StreamBody \
  --proto-root proto/nest \
  --python-out proto/nest
```

## Understanding the Typedef Format

The `typedef.json` files contain field mappings like:

```json
{
  "1": {
    "name": "",
    "type": "message",
    "message_typedef": {
      "1": {"name": "", "type": "bytes"},
      "2": {"name": "", "type": "string"}
    }
  }
}
```

This gets converted to:

```protobuf
message ObservedMessage {
  Field1Message field_1 = 1;
  
  message Field1Message {
    bytes field_1 = 1;
    string field_2 = 2;
  }
}
```

## Improving Field Names

The generated proto files use generic names like `field_1`, `field_2`. You can:

1. **Review the blackbox JSON** to understand what fields contain
2. **Manually edit the proto file** to add meaningful names
3. **Recompile** with protoc

Example improvement:

```protobuf
// Before (auto-generated)
message StreamBodyMessage {
  repeated GetOpMessage field_1 = 1;
}

// After (manually improved)
message StreamBodyMessage {
  repeated GetOpMessage messages = 1;  // List of get operations
}
```

## Generating ObserveTraits.bin

The `ObserveTraits.bin` file is a serialized protobuf request. To generate it:

```python
from proto.nestlabs.gateway import v2_pb2

req = v2_pb2.ObserveRequest(version=2, subscribe=True)
for trait in ["weave.trait.security.BoltLockTrait", ...]:
    filt = req.filter.add()
    filt.trait_type = trait

# Serialize to binary
with open("proto/ObserveTraits.bin", "wb") as f:
    f.write(req.SerializeToString())
```

## Complete Workflow Example

```bash
# 1. Capture messages
python reverse_engineering.py \
  --traits "weave.trait.security.BoltLockTrait" \
  --output-dir captures \
  --limit 3

# 2. Find the latest capture
LATEST=$(ls -td captures/*/ | head -1)

# 3. Generate proto files
python tools/generate_proto.py "$LATEST" \
  --message-name StreamBody \
  --proto-root proto/autogen

# 4. Review the generated proto
cat proto/autogen/streambody.proto

# 5. (Optional) Improve field names manually
# Edit proto/autogen/streambody.proto

# 6. Recompile if you made changes
protoc --proto_path=proto/autogen \
       --python_out=proto/autogen \
       proto/autogen/streambody.proto

# 7. Test the generated code
python -c "
from proto.autogen.nest.observe import streambody_pb2
import sys
with open('$LATEST/00001.raw.bin', 'rb') as f:
    msg = streambody_pb2.StreamBody()
    msg.ParseFromString(f.read())
    print('Success! Parsed', len(msg.field_1), 'messages')
"
```

## Troubleshooting

### protoc not found
Install protoc:
```bash
# macOS
brew install protobuf

# Linux
sudo apt-get install protobuf-compiler

# Or download from https://github.com/protocolbuffers/protobuf/releases
```

### Import errors
Make sure the generated files are in the Python path:
```python
import sys
sys.path.insert(0, 'proto/autogen')
```

### Field type mismatches
If protoc complains about field types, check the typedef and manually fix the proto file.

## Next Steps

1. **Capture more messages** with different traits to get complete typedefs
2. **Merge multiple captures** to build comprehensive proto definitions
3. **Manually refine** field names based on your understanding
4. **Update your integration** to use the improved proto files

## See Also

- `tools/generate_proto.py` - The generation tool
- `docs/REVERSE_ENGINEERING.md` - Original workflow documentation
- `reverse_engineering.py` - Capture tool

