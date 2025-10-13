from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

from typing import Any, Dict, Iterable, Tuple

import blackboxprotobuf as bbp
from requests import HTTPError

from google.protobuf.message import DecodeError

from auth import GetSessionWithAuth
from const import ENDPOINT_OBSERVE, PRODUCTION_HOSTNAME, URL_PROTOBUF
from proto_utils import GetObservePayload, ParseStreamBody, SendGRPCRequest
from proto.nest import rpc_pb2 as rpc

DEFAULT_TRAITS = [
    "nest.trait.user.UserInfoTrait",
    "nest.trait.structure.StructureInfoTrait",
]

PROTO_SCALAR_TYPE_MAP = {
    "bool": "bool",
    "bytes": "bytes",
    "double": "double",
    "enum": "int32",
    "fixed32": "fixed32",
    "fixed64": "fixed64",
    "float": "float",
    "int": "int64",
    "int32": "int32",
    "int64": "int64",
    "sfixed32": "sfixed32",
    "sfixed64": "sfixed64",
    "sint": "sint64",
    "sint32": "sint32",
    "sint64": "sint64",
    "string": "string",
    "uint": "uint64",
    "uint32": "uint32",
    "uint64": "uint64",
    "varint": "uint64",
}

PROTO_RESERVED_WORDS = {
    "package",
    "syntax",
    "import",
    "option",
    "message",
    "enum",
    "repeated",
    "optional",
    "required",
    "map",
    "reserved",
    "returns",
    "rpc",
}


def _sanitize_identifier(name: str, prefix: str) -> str:
    candidate = re.sub(r"\W+", "_", name or "")
    if not candidate:
        candidate = prefix
    if candidate[0].isdigit():
        candidate = f"{prefix}_{candidate}"
    candidate_lower = candidate.lower()
    if candidate_lower in PROTO_RESERVED_WORDS:
        candidate = f"{candidate}_{prefix}"
    return candidate


def _snake_to_camel(name: str) -> str:
    parts = re.split(r"[_\s]+", name)
    return "".join(part.capitalize() for part in parts if part)


def _typedef_to_pseudo_proto(typedef: Dict[str, Dict[str, Any]], message_name: str, depth: int = 0) -> str:
    indent = "  " * depth
    lines = [f"{indent}message {message_name} {{"]
    nested_sections = []
    try:
        field_items = sorted(typedef.items(), key=lambda item: int(item[0]) if str(item[0]).isdigit() else item[0])
    except Exception:
        field_items = typedef.items()

    for field_number, field_info in field_items:
        field_meta = field_info or {}
        field_name = _sanitize_identifier(field_meta.get("name") or f"field_{field_number}", "field")
        field_type = field_meta.get("type", "bytes")
        repeated = bool(field_meta.get("repeated"))

        if isinstance(field_type, (tuple, list)) and field_type:
            # Handle structures like ("message", {...})
            container = field_type
            field_type = container[0]
            if len(container) > 1 and not field_meta.get("message_typedef"):
                field_meta["message_typedef"] = container[1]

        if field_type in {"message", "group"}:
            nested_typedef = field_meta.get("message_typedef") or {}
            nested_name = field_meta.get("message_name") or f"{_snake_to_camel(field_name)}Message"
            nested_sections.append(_typedef_to_pseudo_proto(nested_typedef, nested_name, depth + 1))
            resolved_type = nested_name
        else:
            resolved_type = PROTO_SCALAR_TYPE_MAP.get(field_type, "bytes")

        label = "repeated " if repeated else ""
        lines.append(f"{indent}  {label}{resolved_type} {field_name} = {field_number};")

    if nested_sections:
        lines.append("")
        lines.extend(nested_sections)

    lines.append(f"{indent}}}")
    return "\n".join(lines)


def typedef_to_pseudo_proto(typedef: Dict[str, Dict[str, Any]], root_name: str = "ObservedMessage") -> str:
    return _typedef_to_pseudo_proto(typedef, root_name)


def utc_timestamp(timespec: str = "seconds") -> str:
    """Return a UTC timestamp string with a trailing Z."""
    return datetime.now(UTC).isoformat(timespec=timespec).replace("+00:00", "Z")


def resolve_transport_override(value: str | None) -> str | None:
    if not value:
        return None
    lowered = value.strip().lower()
    if lowered in {"production", "prod", "default"}:
        return URL_PROTOBUF.format(grpc_hostname=PRODUCTION_HOSTNAME["grpc_hostname"])
    return value


def prepare_run_dir(base_dir: Path, traits: Iterable[str]) -> Path:
    base_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    trait_suffix = "_".join(
        _sanitize_identifier(trait.split(".")[-1].lower(), "trait") for trait in traits
    ) or "observe"
    run_dir = base_dir / f"{timestamp}_{trait_suffix}"
    index = 1
    while run_dir.exists():
        run_dir = base_dir / f"{timestamp}_{trait_suffix}_{index}"
        index += 1
    run_dir.mkdir(parents=True, exist_ok=False)
    return run_dir


def capture_observe_stream(
    traits: Iterable[str],
    output_dir: Path,
    limit: int,
    capture_blackbox: bool,
    capture_parsed: bool,
    echo_blackbox: bool,
    echo_parsed: bool,
    transport_override: str | None = None,
) -> Tuple[Path, int]:
    session, access_token, _, transport_url = GetSessionWithAuth()
    print(f"Session supplied transport URL: {transport_url}")

    default_base = URL_PROTOBUF.format(grpc_hostname=PRODUCTION_HOSTNAME["grpc_hostname"])

    def _clean(url: str) -> str:
        return url.rstrip("/")

    base_candidates: list[str] = []
    if transport_override:
        base_candidates.append(_clean(transport_override))
        print(f"Using CLI-specified transport base: {transport_override}")
    if transport_url:
        cleaned_transport = _clean(transport_url)
        if cleaned_transport not in base_candidates:
            base_candidates.append(cleaned_transport)
    default_clean = _clean(default_base)
    if default_clean not in base_candidates:
        base_candidates.append(default_clean)
    if not base_candidates:
        base_candidates.append(default_clean)

    transport_attempts: list[Dict[str, Any]] = []
    response = None
    effective_transport = None
    last_exc: Exception | None = None

    payload = GetObservePayload(list(traits))

    for base in base_candidates:
        print(f"Attempting Observe against base URL: {base}")
        try:
            response = SendGRPCRequest(
                session,
                ENDPOINT_OBSERVE,
                access_token,
                payload,
                base_url=base,
            )
            effective_transport = base
            transport_attempts.append(
                {"base_url": base, "status": getattr(response, "status_code", None)}
            )
            break
        except HTTPError as err:
            status = err.response.status_code if err.response is not None else None
            transport_attempts.append(
                {"base_url": base, "status": status, "error": str(err)}
            )
            print(f"Observe attempt failed for {base}: {err}", file=sys.stderr)
            last_exc = err
        except Exception as err:  # noqa: BLE001
            transport_attempts.append(
                {"base_url": base, "status": None, "error": str(err)}
            )
            print(
                f"Observe attempt raised unexpected error for {base}: {err}",
                file=sys.stderr,
            )
            last_exc = err

    if response is None:
        session.close()
        raise RuntimeError(
            f"Observe request failed for all transports ({len(base_candidates)} attempted)."
        ) from last_exc

    run_dir = prepare_run_dir(output_dir, traits)
    manifest_path = run_dir / "manifest.json"
    config_path = run_dir / "run_config.json"

    manifest: list[Dict[str, Any]] = []
    chunk_count = 0
    interrupted = False
    pending_buffer = bytearray()

    run_metadata = {
        "traits": list(traits),
        "limit": limit,
        "capture_blackbox": capture_blackbox,
        "capture_parsed": capture_parsed,
        "started_at": utc_timestamp(),
        "transport_override": transport_override,
        "transport_from_session": transport_url,
        "transport_effective": effective_transport,
        "transport_attempts": transport_attempts,
    }

    try:
        for chunk in response.iter_content(chunk_size=None):
            if not chunk:
                continue
            pending_buffer.extend(chunk)

            if echo_parsed:
                print(
                    f"[reverse_engineering] received chunk: {len(chunk)} bytes, buffered={len(pending_buffer)}"
                )

            while len(pending_buffer) >= 5:
                compressed_flag = pending_buffer[0]
                message_length = int.from_bytes(pending_buffer[1:5], "big")

                if len(pending_buffer) < 5 + message_length:
                    break

                frame = bytes(pending_buffer[5 : 5 + message_length])
                del pending_buffer[: 5 + message_length]

                if compressed_flag != 0:
                    entry = {
                        "index": chunk_count + 1,
                        "timestamp": utc_timestamp(),
                        "raw_error": f"compressed_frame_{chunk_count + 1:05d}.bin",
                        "parse_error": f"Compressed gRPC-Web frame (flag={compressed_flag}) not supported",
                    }
                    error_path = run_dir / entry["raw_error"]
                    error_path.write_bytes(frame)
                    manifest.append(entry)
                    continue

                try:
                    stream_body = rpc.StreamBody()
                    stream_body.ParseFromString(frame)
                except DecodeError as err:
                    entry = {
                        "index": chunk_count + 1,
                        "timestamp": utc_timestamp(),
                        "raw_error": f"incomplete_frame_{chunk_count + 1:05d}.bin",
                        "parse_error": str(err),
                    }
                    error_path = run_dir / entry["raw_error"]
                    error_path.write_bytes(frame)
                    manifest.append(entry)
                    continue

                chunk_count += 1
                chunk_prefix = f"{chunk_count:05d}"
                raw_path = run_dir / f"{chunk_prefix}.raw.bin"
                raw_path.write_bytes(frame)

                entry = {
                    "index": chunk_count,
                    "timestamp": utc_timestamp(),
                    "raw": raw_path.name,
                }

                if capture_blackbox:
                    try:
                        message_json, typedef = bbp.protobuf_to_json(frame)
                        blackbox_path = run_dir / f"{chunk_prefix}.blackbox.json"
                        blackbox_path.write_text(message_json)

                        typedef_path = run_dir / f"{chunk_prefix}.typedef.json"
                        typedef_path.write_text(json.dumps(typedef, indent=2, sort_keys=True, default=str))

                        pseudo_proto = typedef_to_pseudo_proto(typedef, "ObservedMessage")
                        pseudo_path = run_dir / f"{chunk_prefix}.pseudo.proto"
                        pseudo_path.write_text(pseudo_proto)

                        entry["blackbox"] = {
                            "message": blackbox_path.name,
                            "typedef": typedef_path.name,
                            "pseudo_proto": pseudo_path.name,
                        }

                        if echo_blackbox:
                            print("############ blackbox message ############")
                            print(message_json)
                            print("##########################################")
                    except Exception as err:  # noqa: BLE001
                        entry["blackbox_error"] = str(err)
                        if echo_blackbox:
                            print(f"[reverse_engineering] blackbox decode failed: {err}", file=sys.stderr)

                if capture_parsed:
                    try:
                        parsed = ParseStreamBody(frame)
                        parsed_path = run_dir / f"{chunk_prefix}.parsed.json"
                        parsed_path.write_text(json.dumps(parsed, indent=2, sort_keys=True))
                        entry["parsed"] = parsed_path.name

                        if echo_parsed:
                            print("############ parsed message ############")
                            print(json.dumps(parsed, indent=2))
                            print("########################################")
                    except Exception as err:  # noqa: BLE001
                        entry["parsed_error"] = str(err)
                        if echo_parsed:
                            print(f"[reverse_engineering] structured decode failed: {err}", file=sys.stderr)

                manifest.append(entry)

                if limit and limit > 0 and chunk_count >= limit:
                    break

            if limit and limit > 0 and chunk_count >= limit:
                break

        if pending_buffer:
            pending_path = run_dir / "pending_buffer.bin"
            pending_path.write_bytes(pending_buffer)
            manifest.append(
                {
                    "index": chunk_count + 1,
                    "timestamp": utc_timestamp(),
                    "raw_error": pending_path.name,
                    "parse_error": "Stream ended with incomplete gRPC-Web frame",
                }
            )
    except KeyboardInterrupt:
        interrupted = True
    finally:
        response.close()
        session.close()

    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    run_metadata["completed_at"] = utc_timestamp()
    run_metadata["captured_chunks"] = chunk_count
    run_metadata["interrupted"] = interrupted
    config_path.write_text(json.dumps(run_metadata, indent=2, sort_keys=True))

    if chunk_count == 0 and not interrupted:
        print(
            "Observe request succeeded but no chunks were streamed. "
            "Check trait filters and authentication state.",
            file=sys.stderr,
        )

    if interrupted:
        print("Observe capture interrupted by user; partial data saved.", file=sys.stderr)

    return run_dir, chunk_count


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Capture Nest Observe responses, decode them with blackboxprotobuf, and store artifacts for proto refinement.",
    )
    parser.add_argument(
        "--traits",
        nargs="+",
        default=DEFAULT_TRAITS,
        help="Trait type filters for the Observe request.",
    )
    parser.add_argument(
        "--output-dir",
        default="captures",
        help="Directory root where capture artifacts should be written.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Stop after this many non-empty chunks. Use 0 to keep streaming until interrupted.",
    )
    parser.add_argument(
        "--no-blackbox",
        action="store_true",
        help="Disable blackboxprotobuf decoding.",
    )
    parser.add_argument(
        "--no-parsed",
        action="store_true",
        help="Disable decoding with existing pb2 descriptors.",
    )
    parser.add_argument(
        "--print-blackbox",
        action="store_true",
        help="Echo blackboxprotobuf output to stdout while capturing.",
    )
    parser.add_argument(
        "--print-parsed",
        action="store_true",
        help="Echo descriptor-based JSON output to stdout while capturing.",
    )
    parser.add_argument(
        "--transport-base-url",
        help="Override the gRPC base URL. Use 'production' to force grpc-web.production.nest.com.",
    )
    return parser


def main(argv: list[str]) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    capture_blackbox = not args.no_blackbox
    capture_parsed = not args.no_parsed
    transport_override = resolve_transport_override(args.transport_base_url)

    if not capture_blackbox and not capture_parsed:
        print("At least one of blackbox or descriptor parsing must be enabled.", file=sys.stderr)
        return 1

    output_dir = Path(args.output_dir).expanduser().resolve()

    try:
        run_dir, chunk_count = capture_observe_stream(
            traits=args.traits,
            output_dir=output_dir,
            limit=args.limit,
            capture_blackbox=capture_blackbox,
            capture_parsed=capture_parsed,
            echo_blackbox=args.print_blackbox,
            echo_parsed=args.print_parsed,
            transport_override=transport_override,
        )
    except Exception as err:  # noqa: BLE001
        print(f"Failed to capture Observe stream: {err}", file=sys.stderr)
        return 1

    print(f"Stored {chunk_count} chunk(s) under {run_dir}")
    print("Artifacts:")
    for path in sorted(run_dir.iterdir()):
        print(f" - {path.name}")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
