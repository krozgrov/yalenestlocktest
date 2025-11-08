# How to Use These Tools - Step by Step Guide

## Step 1: Extract IDs from Your Captures

Run the extraction script on your captured messages:

```bash
python extract_ids.py captures/20251013_201107_.../
```

This will show you:
- Structure IDs (like `018C86E39308F29F`)
- User IDs (like `015EADBA454C1770`)
- Device IDs (like `DEVICE_00177A0000060303`)

## Step 2: Understand What's Missing

Run the comparison tool to see what your integration is missing:

```bash
python compare_integration.py captures/20251013_201107_.../ --output comparison.txt
```

This shows you what IDs are available but not being extracted by your integration.

## Step 3: Add Fallback Decoding to Your Integration

### Option A: Use the Fallback Decoder Module

Copy `fallback_decoder.py` to your integration and use it:

```python
# In ha-nest-yale-integration/custom_components/nest_yale_lock/protobuf_handler.py

from .fallback_decoder import FallbackDecoder

class NestProtobufHandler:
    def __init__(self):
        # ... existing code ...
        self.fallback_decoder = FallbackDecoder()
    
    async def _process_message(self, message):
        locks_data = {"yale": {}, "user_id": None, "structure_id": None}
        
        try:
            # Try your existing structured decoding
            locks_data = await self._structured_decode(message)
        except DecodeError:
            # If structured decoding fails, try blackbox fallback
            fallback_result = self.fallback_decoder.decode(message)
            if fallback_result:
                # Extract missing IDs
                if not locks_data.get("structure_id"):
                    structure_id = self.fallback_decoder.extract_structure_id(fallback_result)
                    if structure_id:
                        locks_data["structure_id"] = structure_id
                
                if not locks_data.get("user_id"):
                    user_id = self.fallback_decoder.extract_user_id(fallback_result)
                    if user_id:
                        locks_data["user_id"] = user_id
        
        return locks_data
```

### Option B: Add Extraction Logic Directly

If you prefer not to use blackboxprotobuf in production, you can add extraction logic based on what we found:

```python
# In your protobuf_handler.py, add this helper:

def _extract_structure_id_from_stream(self, stream_body):
    """Extract structure ID from StreamBody when StructureInfoTrait is present."""
    for msg in stream_body.message:
        for get_op in msg.get:
            obj_id = get_op.object.id
            if obj_id and obj_id.startswith("STRUCTURE_"):
                return obj_id.replace("STRUCTURE_", "")
            
            # Also check in the property data
            property_any = getattr(get_op.data, "property", None)
            if property_any:
                try:
                    structure = nest_structure_pb2.StructureInfoTrait()
                    if property_any.Unpack(structure):
                        if structure.legacy_id:
                            # legacy_id format is usually "structure.XXXXX"
                            parts = structure.legacy_id.split(".")
                            if len(parts) > 1:
                                return parts[1]
                except:
                    pass
    return None
```

## Step 4: Use the IDs in Your API Calls

Once you have the structure ID, use it in your command requests:

```python
# In your api_client.py or wherever you send commands

if structure_id:
    headers["X-Nest-Structure-Id"] = structure_id

# When building lock/unlock commands
if user_id:
    request.boltLockActor.originator.resourceId = user_id
```

## Step 5: Test It

1. Capture new messages with your integration running
2. Run `extract_ids.py` to verify IDs are being extracted
3. Check your integration logs to see if structure/user IDs are now available
4. Try sending lock/unlock commands - they should work now!

## Quick Reference

| Tool | What It Does | When to Use |
|------|--------------|-------------|
| `extract_ids.py` | Shows IDs in captured messages | To see what IDs are available |
| `analyze_protobuf.py` | Full analysis of messages | To understand message structure |
| `compare_integration.py` | Compares integration vs available | To find gaps in your integration |
| `fallback_decoder.py` | Extracts IDs from failed decodes | Use in your integration code |

## Example Workflow

```bash
# 1. Capture some messages
python reverse_engineering.py --traits "weave.trait.security.BoltLockTrait" --limit 5

# 2. Extract IDs from the capture
python extract_ids.py captures/LATEST_DIR/

# 3. See what's missing
python compare_integration.py captures/LATEST_DIR/

# 4. Add fallback decoder to your integration (edit code)

# 5. Test with new captures
python reverse_engineering.py --traits "weave.trait.security.BoltLockTrait" --limit 5
python extract_ids.py captures/NEW_DIR/
```

## Troubleshooting

**Q: The IDs aren't being extracted**
- Make sure you're looking at the right messages (ones with StructureInfoTrait/UserInfoTrait)
- Check that blackbox JSON files exist in your capture directory

**Q: How do I know if my integration is using the IDs?**
- Add logging to see if structure_id/user_id are set
- Check your API requests include the X-Nest-Structure-Id header

**Q: Should I use blackboxprotobuf in production?**
- It's optional - you can use it as a fallback when structured decoding fails
- Or you can improve your proto definitions based on what blackbox reveals
- Both approaches work!

