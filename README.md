An effort in prototyping and troublshooting the usage of the Google Nest grcp-web endpoint

# Setup

## Dependencies

There are 2 separate requirements.txt files. This is because the `blackboxprotobuf` package depends on an older version of `protobuf`, but since using a newer version of `protobuf` doesn't break the `blackboxprotobuf` package (and the older version breaks the rest of the scripts here) you should install `blackboxprotobuf` without dependencies.

`pip install -r requirements.txt`
`pip install -r requirements-no-deps.txt --no-deps`

If you accidentally install `blackboxprotobuf` with dependencies and the runtime gets downgraded (you will see `ImportError: cannot import name 'runtime_version'`), simply reinstall the required `protobuf` wheel explicitly: `pip install --upgrade protobuf==6.32.1`.

## Environment File

There is a template for `.env` file called `.env_template`. Simply rename or copy the `.env_template` as `.env` and fill out the 2 variables. For information on how to get the values for the ENV file, read the instructions found [here](https://github.com/chrisjshull/homebridge-nest/tree/master?tab=readme-ov-file#using-a-google-account)


# Usage

Run `python main.py --action status` to authenticate, stream the Observe feed, and print the parsed lock state without sending commands.

- `--action lock` / `--action unlock` will send the corresponding command after the snapshot; add `--dry-run` to preview the payload without dispatching it.
- `--device-id <DEVICE_…>` targets a specific lock when you have multiple Yale devices registered.
- The script always closes the Nest session after the requested action completes, so repeated runs are safe.

# Known Issues

`DecodeError in StreamBody: Error parsing message with type 'nest.rpc.StreamBody'`
This error seems to be due to the incomplete `.proto` and `pb2.py` files. I believe this is probably due to the fact that these files were made from reverse engineering the Version 1 of the Nest APIs, but the "Observe" Endpoint we are making requests to is Version 2 of the APIs.

Because of this, there is a `reverse_engineering.py` that allows you to make an "Observe" request, and then utilize the `blackboxprotobuf` package to return a psuedo-proto message structure of the encoded data returned from the API. The idea is that we can take these outputs and further refine the `.proto` files, and generate new. `pb2.py` bindings for the Nest API Version 2. 

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
