# Reverse Engineering Workflow

This repo now has a repeatable loop for capturing Nest Observe traffic and turning it into typed protobuf descriptors.

## 1. Capture gRPC-Web frames

```
cd yalenestlocktest
source .venv/bin/activate
python reverse_engineering.py \
  --traits nest.trait.user.UserInfoTrait nest.trait.structure.StructureInfoTrait \
           weave.trait.security.BoltLockTrait weave.trait.security.BoltLockSettingsTrait \
           weave.trait.security.BoltLockCapabilitiesTrait weave.trait.security.PincodeInputTrait \
           weave.trait.security.TamperTrait \
  --output-dir captures \
  --limit 2 \
  --print-parsed
```

The updated collector unwraps the gRPC-web envelope, so as soon as a full frame lands you will see `00001.raw.bin`, `00001.parsed.json`, etc. in `captures/<timestamp>/`.

## 2. Merge typedefs & produce a proto

After each capture, feed the typedefs into the generator:

```
python tools/generate_proto.py captures/<timestamp> \
  --message-name ObservedMessage \
  --proto-root proto/autogen
```

This writes `proto/autogen/observedmessage.proto` and compiles it to `proto/autogen/nest/observe/observedmessage_pb2.py` via `protoc`. Those modules get loaded automatically by `proto_utils`.

## 3. Iterate

* Capture more traffic → rerun the generator → the merged typedef fills in new fields.
* If you want to review the intermediate schema, open the generated proto and update field names before checking it in.

With this loop you can capture, decode, and ship descriptor updates without touching the core integration code.***
