A general-purpose protobuf decoder and Nest Yale Lock integration toolkit.

This project provides tools to decode protobuf messages from **any service**, with Nest as a built-in example. The decoder is service-agnostic and can work with custom proto definitions.

# Quick Start

## Installation

```bash
# Install dependencies
pip install -r requirements.txt
pip install -r requirements-no-deps.txt --no-deps

# Optional: For enhanced output formatting
pip install rich

# Optional: For web GUI
pip install flask
```

**Note:** There are 2 separate requirements.txt files because `blackboxprotobuf` depends on an older version of `protobuf`, but using a newer version doesn't break it. If you see `ImportError: cannot import name 'runtime_version'`, reinstall: `pip install --upgrade protobuf==6.32.1`.

## Environment File (for Nest integration)

Copy `.env_template` to `.env` and fill in your Nest credentials. See [instructions here](https://github.com/chrisjshull/homebridge-nest/tree/master?tab=readme-ov-file#using-a-google-account).

# Usage

## General-Purpose Protobuf Decoder

Decode protobuf messages from **any service**:

```bash
# Decode a binary file (auto-detect format)
python proto_decode.py decode file.bin

# Decode from URL (fetch from any service endpoint)
python proto_decode.py decode --url https://api.example.com/protobuf/data

# Decode from URL with authentication
python proto_decode.py decode --url https://api.example.com/data \
  --headers '{"Authorization": "Bearer your_token"}'

# POST request with protobuf payload
python proto_decode.py decode --url https://api.example.com/observe \
  --method POST \
  --post-data request.bin \
  --headers '{"Content-Type": "application/x-protobuf"}'

# Decode with specific message type
python proto_decode.py decode file.bin --message-type nest.rpc.StreamBody

# Decode hex string
python proto_decode.py decode --hex "0a0b48656c6c6f20576f726c64"

# Decode base64
python proto_decode.py decode --base64 "CgtIZWxsbyBXb3JsZA=="

# Use blackboxprotobuf (no proto definition needed!)
python proto_decode.py decode file.bin --blackbox

# Load custom proto files
python proto_decode.py decode file.bin --proto-path ./my_proto_files
```

## Nest-Specific Tools

### Lock Control

```bash
# Check lock status
python nest_tool.py lock --action status

# Lock/unlock device
python nest_tool.py lock --action lock
python nest_tool.py lock --action unlock --device-id DEVICE_00177A0000060303
```

### Trait Decoding

```bash
# Decode all traits (pretty format)
python nest_tool.py decode --format pretty

# Decode as JSON
python nest_tool.py decode --format json
```

## GUI Interface

```bash
# Desktop GUI (Tkinter - built-in)
python gui.py --mode desktop

# Web GUI (requires Flask)
python gui.py --mode web --port 5000
```

## Testing Tools

```bash
# Test a capture file
python test_tool.py file captures/latest/00001.raw.bin

# Test all files in a directory
python test_tool.py directory captures/latest

# Test live stream
python test_tool.py stream --limit 3
```

# Project Structure

## Core Tools (10 files)

**Main Tools:**
- **`proto_decode.py`** - General-purpose protobuf decoder (works with any service!)
  - Supports files, URLs, hex, base64
  - Works with or without proto definitions
  - Service-agnostic architecture
- **`nest_tool.py`** - Nest-specific lock control and trait decoding
- **`gui.py`** - GUI interface (web + desktop)
- **`test_tool.py`** - Unified testing tool
- **`reverse_engineering.py`** - Capture and reverse engineer proto structures

**Supporting Modules:**
- `protobuf_handler.py` - Core protobuf handler
- `protobuf_handler_enhanced.py` - Enhanced handler with full trait decoding
- `auth.py` - Authentication utilities
- `const.py` - Constants
- `proto_utils.py` - Proto utilities

## Legacy Scripts (2 files)

- `main.py` - Original lock control (use `nest_tool.py lock` instead)
- `decode_traits.py` - Original decoder (use `nest_tool.py decode` or `proto_decode.py` instead)

## Utility Scripts (3 files)

- `archive_old_scripts.py` - Archive redundant test/capture scripts
- `archive_dev_tools.py` - Archive development tools
- `test_nest_url_live.py` - Live URL testing script

## Archived Files

Development tools and redundant scripts have been archived to `archive/`:
- `archive/dev_tools/` - Development and proto refinement tools
- `archive/test_scripts/` - Redundant test scripts
- `archive/capture_scripts/` - Redundant capture scripts
- `archive/decode_scripts/` - Redundant decode/extract scripts
- `archive/analysis_scripts/` - Analysis scripts

All archived files are preserved in git history.

# Advanced Usage

## Decoding from URLs

The decoder can fetch protobuf data directly from any service endpoint:

```bash
# Simple GET request
python proto_decode.py decode --url https://api.example.com/protobuf/data

# With authentication
python proto_decode.py decode --url https://api.example.com/data \
  --headers '{"Authorization": "Bearer token", "X-API-Key": "key"}'

# POST request with protobuf payload
python proto_decode.py decode --url https://api.example.com/observe \
  --method POST \
  --post-data request.bin \
  --headers '{"Content-Type": "application/x-protobuf"}'

# Stream large responses
python proto_decode.py decode --url https://api.example.com/stream \
  --stream --timeout 60
```

## Using Custom Proto Files

The general decoder can work with any proto definitions:

```bash
# Load proto files from a directory
python proto_decode.py decode file.bin --proto-path ./my_proto_files

# Use a Python module containing proto definitions
python proto_decode.py decode file.bin --proto-module mypackage.proto
```

## Decoding Without Proto Definitions

Use blackboxprotobuf to decode messages without proto files:

```bash
python proto_decode.py decode file.bin --blackbox
```

This will attempt to decode the message structure automatically and generate a type definition. 

## Automating Observe captures

The reverse engineering workflow now streams Observe responses into timestamped capture folders so the raw payloads, the `blackboxprotobuf` decodes, and the descriptor-based JSON all stay in sync. Run it after exporting your Google authentication cookies:

```bash
python reverse_engineering.py \
  --traits nest.trait.user.UserInfoTrait nest.trait.structure.StructureInfoTrait \
  --limit 5 \
  --output-dir captures
  # optionally: --print-blackbox --print-parsed
  # optionally: --transport-base-url production  # force grpc-web.production.nest.com
```

Each run creates a new subdirectory under `captures/` containing:

- `#####.raw.bin` — the original binary chunk for later replays.
- `#####.blackbox.json`, `#####.typedef.json`, `#####.pseudo.proto` — the raw `blackboxprotobuf` output and an auto-generated pseudo `.proto` scaffold to refine by hand.
- `#####.parsed.json` — whatever could be decoded with the existing pb2 descriptors.
- `manifest.json` and `run_config.json` — metadata describing the session for tooling or audits.

Use the pseudo `.proto` files as a starting point, refine the field names and types manually, and then regenerate the pb2 bindings with `protoc` once you are satisfied with the updated definitions.

If you receive `Observe response status: 400`, the Nest transport rejected the request. Refresh your auth by:

```bash
python auth.py  # verify access token, userid, and transport_url
python reverse_engineering.py --limit 1 --print-parsed --transport-base-url production
```

Make sure the `.env` values (`ISSUE_TOKEN`, `COOKIES`) are current (copy a fresh session cookie block from accounts.google.com and home.nest.com), then retry the Observe capture.
The capture script will automatically fall back to `grpc-web.production.nest.com` if the per-session transport host returns an HTTP error, and `run_config.json` records each attempt (`transport_attempts`) so you can see which endpoint finally worked.

## Regenerating protobuf bindings

Once you hand-edit a `.proto` file to reflect new field names or message layouts (for example `proto/nest/rpc.proto` after examining a capture’s `pseudo.proto` scaffold), regenerate the Python bindings so `ParseStreamBody` can pick up the descriptor changes:

```bash
protoc -I. --python_out=. proto/nest/rpc.proto
```

Re-run the capture script against an existing `*.raw.bin` sample to confirm the decoded JSON now contains the expected fields. It’s useful to keep a short regression loop, for example:

```bash
python - <<'PY'
from pathlib import Path
from proto_utils import ParseStreamBody
import json
raw = Path("captures/<run>/00001.raw.bin").read_bytes()
print(json.dumps(ParseStreamBody(raw), indent=2))
PY
```

If decoding fails after a change, compare the new `pseudo.proto` output from a fresh capture to the edited `.proto` to work out which field numbers or types still need to be updated.
