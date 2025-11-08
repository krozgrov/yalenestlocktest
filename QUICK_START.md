# Quick Start Guide - Protobuf Analysis Tools

## Quick Commands

### 1. Analyze a capture directory
```bash
python analyze_protobuf.py captures/20251013_201107_.../ --output analysis.txt
```

### 2. Compare integration vs blackbox decoding
```bash
python compare_integration.py captures/20251013_201107_.../ --output comparison.txt
```

### 3. Use fallback decoder in code
```python
from fallback_decoder import FallbackDecoder

decoder = FallbackDecoder()
result = decoder.decode(raw_bytes)
if result:
    structure_id = decoder.extract_structure_id(result)
    user_id = decoder.extract_user_id(result)
```

## What Each Tool Does

| Tool | Purpose | Output |
|------|---------|--------|
| `analyze_protobuf.py` | Analyzes captured messages to find missing fields | Text report + optional JSON |
| `compare_integration.py` | Compares integration decoding vs blackbox | Comparison report showing gaps |
| `fallback_decoder.py` | Fallback decoder module for failed messages | Python module (importable) |

## Typical Workflow

1. **Capture messages** (if you haven't already):
   ```bash
   python reverse_engineering.py --traits "weave.trait.security.BoltLockTrait" --limit 5
   ```

2. **Analyze what's available**:
   ```bash
   python analyze_protobuf.py captures/LATEST_DIR/
   ```

3. **Compare with integration**:
   ```bash
   python compare_integration.py captures/LATEST_DIR/
   ```

4. **Review reports** to identify:
   - Missing structure/user IDs
   - Fields not being extracted
   - Opportunities for improvement

## Installation

Make sure you have the dependencies:
```bash
pip install -r requirements.txt
pip install -r requirements-no-deps.txt --no-deps
```

## See Also

- `PROTOBUF_ANALYSIS.md` - Detailed documentation
- `SUMMARY.md` - Summary of findings and recommendations

