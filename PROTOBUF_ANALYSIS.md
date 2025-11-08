# Protobuf Decoding Analysis Tools

This document describes the tools available for analyzing and improving protobuf message decoding in the Nest Yale Lock integration.

## Overview

The Nest API uses protobuf messages that are partially reverse-engineered. Some messages can be decoded using structured proto definitions, while others fail with `DecodeError`. The tools in this directory help:

1. **Analyze captured messages** to understand what data is available
2. **Compare decoding methods** (structured vs blackboxprotobuf)
3. **Identify missing fields** that could be extracted
4. **Generate fallback decoders** for failed messages

## Tools

### 1. `analyze_protobuf.py` - Message Analysis Tool

Analyzes captured protobuf messages to identify:
- Fields available in blackboxprotobuf but not in structured decoding
- Device, structure, and user IDs found in messages
- Common patterns in missing fields

**Usage:**
```bash
python analyze_protobuf.py captures/20251013_201107_.../ --output analysis_report.txt --json analysis.json
```

**Output:**
- Text report showing summary statistics and missing fields
- Optional JSON file with detailed analysis

### 2. `compare_integration.py` - Integration Comparison Tool

Compares what the `ha-nest-yale-integration` currently decodes vs what's available in blackboxprotobuf decoded data.

**Usage:**
```bash
python compare_integration.py captures/20251013_201107_.../ --output comparison_report.txt --json comparison.json
```

**Output:**
- Comparison report showing:
  - Devices found by integration vs blackbox
  - Structures found by integration vs blackbox
  - Users found by integration vs blackbox
  - Fields missing in integration decoding

### 3. `fallback_decoder.py` - Fallback Decoder Module

Provides a fallback decoder using `blackboxprotobuf` for messages that fail structured decoding.

**Features:**
- Decodes protobuf messages when structured decoding fails
- Extracts device, structure, and user information
- Can be integrated into the main integration as a fallback

**Example Usage:**
```python
from fallback_decoder import FallbackDecoder

decoder = FallbackDecoder()
result = decoder.decode(raw_protobuf_bytes)
if result:
    device_info = decoder.extract_device_info(result)
    structure_id = decoder.extract_structure_id(result)
    user_id = decoder.extract_user_id(result)
```

## Workflow

### Step 1: Capture Messages

Use `reverse_engineering.py` to capture protobuf messages:

```bash
python reverse_engineering.py \
  --traits "nest.trait.user.UserInfoTrait" \
           "nest.trait.structure.StructureInfoTrait" \
           "weave.trait.security.BoltLockTrait" \
  --output-dir captures \
  --limit 10
```

### Step 2: Analyze Captures

Analyze the captured messages to see what's available:

```bash
python analyze_protobuf.py captures/20251013_201107_.../
```

### Step 3: Compare with Integration

Compare what the integration decodes vs what's available:

```bash
python compare_integration.py captures/20251013_201107_.../
```

### Step 4: Review Findings

Review the reports to identify:
- Missing device/structure/user IDs
- Fields that could be extracted
- Opportunities to improve proto definitions

## Integration with ha-nest-yale-integration

The `fallback_decoder.py` module can be integrated into the main integration to provide fallback decoding when structured decoding fails. This would help extract additional information like structure IDs and user IDs that might be missing.

### Potential Integration Points

1. **In `protobuf_handler.py`**: Add fallback decoding when `DecodeError` occurs
2. **For missing structure/user IDs**: Use blackbox decoder to extract IDs when structured decoding doesn't provide them
3. **For additional traits**: Extract trait information from blackbox decoded data

### Example Integration

```python
from fallback_decoder import FallbackDecoder

class NestProtobufHandler:
    def __init__(self):
        # ... existing code ...
        self.fallback_decoder = FallbackDecoder()
    
    async def _process_message(self, message):
        try:
            # Try structured decoding first
            locks_data = await self._structured_decode(message)
        except DecodeError:
            # Fallback to blackbox decoding
            fallback_result = self.fallback_decoder.decode(message)
            if fallback_result:
                # Extract missing information
                if not locks_data.get("structure_id"):
                    locks_data["structure_id"] = self.fallback_decoder.extract_structure_id(fallback_result)
                if not locks_data.get("user_id"):
                    locks_data["user_id"] = self.fallback_decoder.extract_user_id(fallback_result)
        return locks_data
```

## Findings from Issue #5

Based on [issue #5](https://github.com/krozgrov/ha-nest-yale-integration/issues/5), the main problems are:

1. **Structure ID extraction**: The integration may not be properly extracting structure IDs from protobuf messages
2. **User ID extraction**: Similar issues with user ID extraction
3. **Incomplete proto definitions**: Some message types are not fully mapped

The tools in this directory can help identify:
- Where structure/user IDs appear in the blackbox decoded data
- Whether they're being extracted correctly by the integration
- What fields need to be added to proto definitions

## Next Steps

1. Run analysis on existing captures to identify gaps
2. Use findings to improve proto definitions or add fallback decoding
3. Test improved decoding with new captures
4. Integrate improvements into the main integration

## Dependencies

- `blackboxprotobuf`: For fallback decoding
- `protobuf`: For structured decoding
- Standard Python libraries: `json`, `pathlib`, `argparse`

Install with:
```bash
pip install blackboxprotobuf protobuf
```

