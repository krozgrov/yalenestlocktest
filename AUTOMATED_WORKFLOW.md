# Automated Workflow - Quick Reference

## Quick Start

Run the complete automated workflow:

```bash
# Option 1: Bash script (simpler)
./automate_workflow.sh

# Option 2: Python script (more control)
python automate_workflow.py
```

## What It Does

The automated workflow:
1. ✅ **Captures** protobuf messages from Nest API
2. ✅ **Extracts** structure/user/device IDs
3. ✅ **Generates** `.proto` files from typedefs
4. ✅ **Shows** results and next steps

## Usage Examples

### Full Workflow (Capture + Generate)

```bash
# Capture new messages and generate proto files
python automate_workflow.py

# With custom traits
python automate_workflow.py --traits "weave.trait.security.BoltLockTrait" --limit 5
```

### Use Existing Captures

```bash
# Skip capture, use existing capture directory
python automate_workflow.py --skip-capture --use-existing captures/20251013_.../

# Or let it find the latest automatically
python automate_workflow.py --skip-capture
```

### Customize Output

```bash
# Custom message name and output location
python automate_workflow.py \
  --message-name MyMessage \
  --proto-root proto/custom \
  --skip-protoc
```

### Skip Steps

```bash
# Skip ID extraction (faster)
python automate_workflow.py --skip-extract

# Skip protoc compilation (just generate proto)
python automate_workflow.py --skip-protoc
```

## Output

The workflow generates:

1. **Proto file**: `proto/autogen/streambodymessage.proto`
   - Protobuf definition file
   - Can be edited to improve field names

2. **Python bindings** (if protoc is available):
   - `proto/autogen/nest/observe/streambodymessage_pb2.py`
   - Import and use in your code

## After Running

### 1. Review Generated Proto

```bash
cat proto/autogen/streambodymessage.proto
```

### 2. Improve Field Names (Optional)

Edit the proto file to add meaningful names:
```protobuf
message StreamBodyMessage {
  repeated GetOpMessage messages = 1;  // Better than field_1
}
```

### 3. Compile to pb2 (if skipped)

```bash
protoc --proto_path=proto/autogen \
       --python_out=proto/autogen \
       proto/autogen/streambodymessage.proto
```

### 4. Use in Your Code

```python
from proto.autogen.nest.observe import streambodymessage_pb2

msg = streambodymessage_pb2.StreamBodyMessage()
msg.ParseFromString(raw_bytes)
```

## Troubleshooting

### No typedef files found
- Make sure you ran `reverse_engineering.py` with blackbox enabled
- Check that `*.typedef.json` files exist in the capture directory

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

## Scripts Available

| Script | Type | Best For |
|--------|------|----------|
| `automate_workflow.sh` | Bash | Quick runs, simple automation |
| `automate_workflow.py` | Python | More control, better error handling |

## Complete Example

```bash
# 1. Run automated workflow
python automate_workflow.py --limit 3

# 2. Review output
cat proto/autogen/streambodymessage.proto

# 3. Compile (if protoc available)
protoc --proto_path=proto/autogen \
       --python_out=proto/autogen \
       proto/autogen/streambodymessage.proto

# 4. Test
python -c "
from proto.autogen.nest.observe import streambodymessage_pb2
print('Success! Proto files generated and compiled.')
"
```

## Integration with Your Workflow

You can integrate this into your development process:

```bash
# In your Makefile or CI/CD
proto: capture generate
	@echo "Generating proto files..."
	python automate_workflow.py --skip-capture

capture:
	python reverse_engineering.py --traits "..." --limit 5

generate:
	python automate_workflow.py --skip-capture
```

## Next Steps

1. **Run the workflow** to generate proto files
2. **Review** the generated proto files
3. **Improve** field names based on your understanding
4. **Compile** with protoc
5. **Use** in your integration code

See `COMPLETE_WORKFLOW.md` for detailed step-by-step instructions.

