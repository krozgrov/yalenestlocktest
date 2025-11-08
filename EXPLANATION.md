# Simple Explanation - What These Tools Do

## The Problem

Your Nest Yale Lock integration uses protobuf messages to communicate with Nest's servers. There are two ways to decode these messages:

1. **Structured decoding** - Uses `.proto` files (like a blueprint) to decode messages
   - ✅ Works well for messages that match the blueprint
   - ❌ Fails with `DecodeError` for messages that don't match

2. **Blackbox decoding** - Uses `blackboxprotobuf` library to decode ANY message
   - ✅ Can decode messages even without a blueprint
   - ❌ Results are less structured (just field numbers, not names)

## What I Created

### Tool 1: `analyze_protobuf.py`
**What it does:** Looks at captured protobuf messages and shows you:
- What data is available in the messages
- What fields are being decoded vs what's being missed
- Device IDs, structure IDs, user IDs that are in the messages

**Why it's useful:** Helps you see what information is "hiding" in messages that aren't being decoded properly.

**Example:**
```
You run: python analyze_protobuf.py captures/20251013_.../
Output: "Found structure ID STRUCTURE_018C86E39308F29F in blackbox but not in parsed"
```

### Tool 2: `compare_integration.py`
**What it does:** Compares what your Home Assistant integration currently extracts vs what's actually available in the messages.

**Why it's useful:** Shows you exactly what you're missing - like structure IDs or user IDs that should be extracted but aren't.

**Example:**
```
You run: python compare_integration.py captures/20251013_.../
Output: 
  Integration found: 0 structures
  Blackbox found: 1 structure (STRUCTURE_018C86E39308F29F)
  ⚠️ Missing in Integration: 1 structure
```

### Tool 3: `fallback_decoder.py`
**What it does:** A Python module that can decode protobuf messages when structured decoding fails.

**Why it's useful:** You can add this to your integration so when structured decoding fails, it falls back to blackbox decoding to extract missing information like structure IDs.

**Example usage in code:**
```python
# In your integration's protobuf_handler.py
from fallback_decoder import FallbackDecoder

decoder = FallbackDecoder()
result = decoder.decode(failed_message_bytes)
if result:
    structure_id = decoder.extract_structure_id(result)  # Gets the structure ID!
```

## The Workflow

1. **You have captured messages** (from `reverse_engineering.py`) in the `captures/` folder
2. **Run the analysis tools** to see what's in those messages
3. **See what's missing** - like structure IDs that should be extracted
4. **Use the fallback decoder** to extract that missing information

## Real-World Example

Based on [issue #5](https://github.com/krozgrov/ha-nest-yale-integration/issues/5), the problem is:
- The integration can't get structure/user IDs properly
- But these IDs ARE in the protobuf messages
- They're just not being extracted correctly

**Solution:**
1. Run `compare_integration.py` to confirm structure IDs are in the messages but not extracted
2. Use `fallback_decoder.py` in your integration to extract them when structured decoding fails
3. Now your integration can get the structure/user IDs it needs!

## Quick Test

Try this to see what's in your captures:

```bash
# See what devices/structures/users are in the messages
python analyze_protobuf.py captures/20251013_201107_.../ --output report.txt

# Compare with what the integration extracts
python compare_integration.py captures/20251013_201107_.../ --output comparison.txt
```

The reports will show you exactly what data is available but not being used.

