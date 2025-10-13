#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from copy import deepcopy
from pathlib import Path
from typing import Dict, Any, Iterable

try:
    from reverse_engineering import typedef_to_pseudo_proto
except ModuleNotFoundError:
    import importlib.util
    import sys

    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    spec = importlib.util.spec_from_file_location(
        "reverse_engineering", project_root / "reverse_engineering.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    typedef_to_pseudo_proto = module.typedef_to_pseudo_proto

FieldType = Dict[str, Any]
Typedef = Dict[str, FieldType]


def merge_typedef(dest: Typedef, src: Typedef) -> None:
    for field, meta in src.items():
        if field not in dest:
            dest[field] = deepcopy(meta)
            continue

        dest_meta = dest[field]
        for key, value in meta.items():
            if key == "message_typedef":
                dest_meta.setdefault("message_typedef", {})
                merge_typedef(dest_meta["message_typedef"], value)
            elif key == "repeated":
                dest_meta["repeated"] = dest_meta.get("repeated") or value
            elif key == "type":
                dest_meta.setdefault("type", value)
            elif key == "name":
                if not dest_meta.get("name") and value:
                    dest_meta["name"] = value
            elif key == "message_name":
                if not dest_meta.get("message_name") and value:
                    dest_meta["message_name"] = value
            else:
                dest_meta.setdefault(key, value)


def load_typedefs(files: Iterable[Path]) -> Typedef:
    merged: Typedef = {}
    for file in files:
        with file.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        merge_typedef(merged, data)
    return merged


def write_proto(proto_root: Path, message_name: str, typedef: Typedef) -> Path:
    proto_root.mkdir(parents=True, exist_ok=True)
    proto_path = proto_root / f"{message_name.lower()}.proto"
    content = [
        'syntax = "proto3";',
        "package nest.observe;",
        "",
        typedef_to_pseudo_proto(typedef, message_name),
        "",
    ]
    proto_path.write_text("\n".join(content), encoding="utf-8")
    return proto_path


def run_protoc(proto_path: Path, proto_root: Path, python_out: Path, protoc: str) -> None:
    python_out.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            [
                protoc,
                f"--proto_path={proto_root}",
                f"--python_out={python_out}",
                str(proto_path.relative_to(proto_root)),
            ],
            check=True,
        )
    except subprocess.CalledProcessError as err:
        raise RuntimeError(f"protoc failed: {err}") from err


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge blackboxprotobuf typedefs and generate a proto / pb2 module."
    )
    parser.add_argument(
        "capture_dir",
        type=Path,
        help="Capture directory containing *.typedef.json files.",
    )
    parser.add_argument(
        "--message-name",
        default="ObservedMessage",
        help="Root message name to use in the generated proto.",
    )
    parser.add_argument(
        "--proto-root",
        type=Path,
        default=Path("proto/autogen"),
        help="Directory where the generated proto file should live.",
    )
    parser.add_argument(
        "--python-out",
        type=Path,
        default=None,
        help="Directory to write the generated *_pb2.py files (defaults to proto-root).",
    )
    parser.add_argument(
        "--protoc",
        default="protoc",
        help="Path to the protoc compiler.",
    )
    parser.add_argument(
        "--skip-protoc",
        action="store_true",
        help="Generate the proto but skip compiling it with protoc.",
    )
    args = parser.parse_args()

    typedef_files = sorted(args.capture_dir.glob("*.typedef.json"))
    if not typedef_files:
        raise SystemExit(f"No typedef files found in {args.capture_dir}")

    merged = load_typedefs(typedef_files)
    proto_root = args.proto_root.resolve()
    python_out = args.python_out.resolve() if args.python_out else proto_root
    proto_path = write_proto(proto_root, args.message_name, merged)

    if not args.skip_protoc:
        run_protoc(proto_path, proto_root, python_out, args.protoc)

    print(f"Generated proto at {proto_path}")
    if not args.skip_protoc:
        print(f"Generated pb2 under {python_out} (package nest.observe)")


if __name__ == "__main__":
    main()
