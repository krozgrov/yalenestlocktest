# Quick Fix - Add ID Extraction in 2 Minutes

## The Problem
Your integration isn't extracting structure_id and user_id from protobuf messages, even though they're there.

## The Solution
Add these 6 lines of code to your `protobuf_handler.py`.

## Step 1: Open the file
```bash
cd ha-nest-yale-integration
code custom_components/nest_yale_lock/protobuf_handler.py
# or use your favorite editor
```

## Step 2: Find this section (around line 152)
```python
for msg in self.stream_body.message:
    for get_op in msg.get:
        obj_id = get_op.object.id if get_op.object.id else None
        obj_key = get_op.object.key if get_op.object.key else "unknown"
        
        property_any = getattr(get_op.data, "property", None)
```

## Step 3: Add this code RIGHT AFTER `obj_key = ...`
```python
for msg in self.stream_body.message:
    for get_op in msg.get:
        obj_id = get_op.object.id if get_op.object.id else None
        obj_key = get_op.object.key if get_op.object.key else "unknown"
        
        # ADD THESE 6 LINES:
        # Extract structure ID from object ID if present
        if obj_id and obj_id.startswith("STRUCTURE_"):
            structure_id = obj_id.replace("STRUCTURE_", "")
            if not locks_data.get("structure_id"):
                locks_data["structure_id"] = structure_id
                _LOGGER.debug("Extracted structure_id: %s", structure_id)
        
        # Extract user ID from object ID if present  
        if obj_id and obj_id.startswith("USER_"):
            user_id = obj_id.replace("USER_", "")
            if not locks_data.get("user_id"):
                locks_data["user_id"] = user_id
                _LOGGER.debug("Extracted user_id: %s", user_id)
        
        property_any = getattr(get_op.data, "property", None)
```

## Step 4: Test it
```bash
# In yalenestlocktest
python main.py --action status
```

You should now see structure_id and user_id in the output!

## That's it!
This extracts the IDs directly from the `obj_id` field when they appear as "STRUCTURE_XXXXX" or "USER_XXXXX", which is exactly what we found in your captures.

## Verify it works
Check your integration logs - you should see:
```
DEBUG: Extracted structure_id: 018C86E39308F29F
DEBUG: Extracted user_id: 015EADBA454C1770
```

## Next: Use the IDs
Make sure your API calls use these IDs:
- `headers["X-Nest-Structure-Id"] = structure_id` when sending commands
- `request.boltLockActor.originator.resourceId = user_id` in lock/unlock requests

See `INTEGRATION_EXAMPLE.py` for more details on using the IDs in API calls.

