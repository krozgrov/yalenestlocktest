# File Organization Summary

## Core Files (Keep in Root) - 10 files

These are the essential files users need:

1. **`proto_decode.py`** - General-purpose protobuf decoder (main tool)
2. **`nest_tool.py`** - Nest-specific wrapper
3. **`gui.py`** - GUI interface
4. **`test_tool.py`** - Unified testing tool
5. **`reverse_engineering.py`** - Proto refinement tool
6. **`protobuf_handler.py`** - Core protobuf handler
7. **`protobuf_handler_enhanced.py`** - Enhanced handler with full trait decoding
8. **`auth.py`** - Authentication utilities
9. **`const.py`** - Constants
10. **`proto_utils.py`** - Proto utilities

## Legacy Files (Keep for Reference) - 2 files

These are kept for backward compatibility:

1. **`main.py`** - Original lock control (use `nest_tool.py lock` instead)
2. **`decode_traits.py`** - Original decoder (use `proto_decode.py` or `nest_tool.py decode` instead)

## Utility Scripts (Keep) - 3 files

1. **`archive_old_scripts.py`** - Cleanup tool
2. **`archive_dev_tools.py`** - Archive development tools
3. **`test_nest_url_live.py`** - Live URL test script

## Development Tools (Archive) - 18 files

These are useful for development but not needed for end users:

1. `automate_workflow.py`
2. `compare_typedef_with_proto.py`
3. `enhanced_protobuf_handler.py` (duplicate)
4. `fallback_decoder.py`
5. `find_serial_number.py`
6. `fix_proto_imports.py`
7. `generate_ha_proto_files.py`
8. `homekit_protobuf_patch.py`
9. `map_typedef_to_proto.py`
10. `protobuf_manager.py`
11. `refine_proto_from_blackbox.py`
12. `refine_proto_workflow.py`
13. `show_decoded_output.py`
14. `sync_with_homebridge_nest.py`
15. `update_all_proto_files.py`
16. `update_proto_from_captures.py`
17. `INTEGRATION_EXAMPLE.py`
18. `test_nest_url.py` (duplicate)

## Summary

- **Core files**: 10 (essential)
- **Legacy files**: 2 (for reference)
- **Utility scripts**: 3 (helpful tools)
- **Development tools**: 18 (can be archived)

**Total in root after cleanup: 15 Python files** (down from 33)

