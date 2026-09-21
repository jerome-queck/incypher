"""Dependency-free inspection of small immutable snapshots, never extraction."""
from __future__ import annotations

import hashlib
import io
import json
import re
import stat
import struct
import zipfile
from dataclasses import asdict, dataclass

from agent_ext.resources import positive_int

OPERATIONS = frozenset({"identify", "text", "hex", "strings", "zip_list"})
VERSION = "triage-v1"


class InspectionError(ValueError):
    pass


@dataclass(frozen=True)
class Limits:
    input_bytes: int = 1024 * 1024
    preview_bytes: int = 1024
    strings: int = 32
    string_bytes: int = 128
    archive_entries: int = 100
    archive_directory_bytes: int = 64 * 1024
    archive_expanded_bytes: int = 16 * 1024 * 1024
    output_bytes: int = 8192

    def __post_init__(self):
        if not all(positive_int(v) for v in asdict(self).values()):
            raise ValueError("limits must be positive integers")
        # Prevent accidental removal of the small-workload boundary.
        if self.input_bytes > 8 * 1024 * 1024 or self.output_bytes < 1024:
            raise ValueError("unsupported snapshot or output budget")


def encode(value) -> bytes:
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")


def observation_key(scope, digest: str, operation: str, offset: int, limits: Limits):
    """Attempt-independent identity; no cache or evidence store is created here."""
    record = [VERSION, scope.challenge_id, scope.material_ref,
              scope.instance_generation, digest, operation, offset, asdict(limits)]
    return "sha256:" + hashlib.sha256(encode(record)).hexdigest()


def safe_member(name: str):
    parts = name.replace("\\", "/").split("/")
    if (not name or name.startswith(("/", "\\")) or ".." in parts
            or ":" in name or "\x00" in name):
        raise InspectionError("unsafe_archive_path")


def zip_members(data: bytes, limits: Limits):
    # Preflight before ZipFile allocates one object per central-directory member.
    end = data.rfind(b"PK\x05\x06", max(0, len(data) - 65557))
    if end < 0 or end + 22 > len(data):
        raise InspectionError("malformed_archive")
    _, disk, start_disk, disk_count, count, size, offset, comment = struct.unpack_from(
        "<4s4H2LH", data, end)
    if (end + 22 + comment != len(data) or disk or start_disk or disk_count != count
            or count == 65535 or size == 0xFFFFFFFF or offset == 0xFFFFFFFF):
        raise InspectionError("unsupported_archive")
    if count > limits.archive_entries or size > limits.archive_directory_bytes:
        raise InspectionError("archive_metadata_limit")
    if offset + size != end:
        raise InspectionError("malformed_archive")
    # Verify actual records/count, so forged EOCD counts cannot bypass the bound.
    position = offset
    for _ in range(count):
        if position + 46 > end or data[position:position + 4] != b"PK\x01\x02":
            raise InspectionError("malformed_archive")
        name_len, extra_len, comment_len = struct.unpack_from("<3H", data, position + 28)
        position += 46 + name_len + extra_len + comment_len
        if position > end:
            raise InspectionError("malformed_archive")
    if position != end:
        raise InspectionError("malformed_archive")
    entries, total = [], 0
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for member in archive.infolist():
            safe_member(member.orig_filename)
            if stat.S_ISLNK(member.external_attr >> 16):
                raise InspectionError("archive_symlink")
            if len(member.filename.encode("utf-8")) > 512:
                raise InspectionError("archive_name_limit")
            total += member.file_size
            if total > limits.archive_expanded_bytes:
                raise InspectionError("archive_expansion_limit")
            entries.append(dict(name=member.filename, declared_bytes=member.file_size,
                                compressed_bytes=member.compress_size,
                                encrypted=bool(member.flag_bits & 1)))
    return dict(entries=entries, entries_seen=len(entries),
                declared_expanded_bytes=total, extracted=False,
                sizes_verified=False, complete=True)


def inspect(data: bytes, operation: str, offset: int, limits: Limits):
    if operation not in OPERATIONS:
        raise InspectionError("unsupported_operation")
    if type(offset) is not int or offset < 0 or offset > len(data):
        raise InspectionError("invalid_offset")
    if operation not in {"text", "hex"} and offset:
        raise InspectionError("invalid_offset")
    if len(data) > limits.input_bytes:
        raise InspectionError("input_limit")
    result = dict(operation=operation, source_bytes=len(data), truncated=False)
    if operation == "identify":
        signatures = ((b"\x7fELF", "elf"), (b"PK\x03\x04", "zip"),
                      (b"PK\x05\x06", "zip"), (b"\x1f\x8b", "gzip"),
                      (b"%PDF-", "pdf"), (b"\x89PNG\r\n\x1a\n", "png"))
        result.update(kind=next((kind for magic, kind in signatures
                                 if data.startswith(magic)), "unknown"),
                      method="header_signature", bytes_inspected=min(len(data), 8))
    elif operation in {"text", "hex"}:
        sample = data[offset:offset + limits.preview_bytes]
        result.update(offset=offset, bytes_inspected=len(sample),
                      truncated=offset + len(sample) < len(data) or offset > 0)
        if operation == "hex":
            result["hex"] = sample.hex()
        else:
            result.update(text=sample.decode("utf-8", errors="replace"),
                          encoding="utf-8-with-replacement")
    elif operation == "strings":
        matches = []
        scanned = len(data)
        for match in re.finditer(rb"[\x20-\x7e]{4,}", data):
            if len(matches) >= limits.strings:
                result["truncated"] = True
                scanned = match.start()
                break
            value = match.group()[:limits.string_bytes]
            shortened = len(value) < match.end() - match.start()
            result["truncated"] |= shortened
            matches.append(dict(offset=match.start(), text=value.decode("ascii"),
                                shortened=shortened))
        result.update(matches=matches, bytes_scanned=scanned,
                      scan_complete=scanned == len(data), minimum_length=4)
    else:
        result.update(zip_members(data, limits))
    # Include explicit loss of content instead of returning a cut JSON string.
    if len(encode(result)) > limits.output_bytes:
        result = dict(operation=operation, source_bytes=len(data), truncated=True,
                      truncation_reason="observation_limit", observation_omitted=True)
    return result
