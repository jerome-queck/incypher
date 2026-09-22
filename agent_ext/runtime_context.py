"""Trusted per-challenge context bound around the inherited solver lifecycle."""

from __future__ import annotations

import hashlib
import json
import os
import math
import re
import time
import uuid
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path

from .playbooks import normalize_category


_CURRENT: ContextVar["AttemptContext | None"] = ContextVar("attempt_context", default=None)
_MAX_FILES = 128
_MAX_HASH_BYTES = 64 * 1024 * 1024
DYNAMIC_CHALLENGE_TYPES = frozenset({"dynamic_iac", "dynamic", "container", "service"})
MAX_FINDING_BYTES = 384
_RUNTIME_REDACTION_ENV = ("CTF_TOKEN", "CTF_SESSION", "LLM_API_KEY")

_FINDING_DENIED_TERMS = re.compile(
    r"(?i)\b(?:flag|flags|secret|secrets|password|passwords|passwd|credential|"
    r"credentials|candidate|candidates|token|tokens|bearer|authorization|"
    r"auth|authenticate|authenticated|authentication|login|logon|account|"
    r"username|user[-_ ]?id|passcode|cookie|cookies|api[-_ ]?key|"
    r"access[-_ ]?key|private[-_ ]?key|connection|connections|connect|connected|"
    r"connecting|endpoint|endpoints|host|hosts|hostname|hostnames|port|ports|"
    r"socket|sockets|listener|listeners|remote|ssh|tcp|udp|netcat)\b"
)
_FINDING_FLAG = re.compile(r"(?i)\b[A-Z0-9_-]{0,32}(?:flag|ctf|incypher)\s*\{")
_FINDING_URL = re.compile(
    r"(?i)(?:\b[a-z][a-z0-9+.-]{1,31}://|\bwww\.|"
    r"\b(?:[a-z0-9-]+\.)+[a-z]{2,63}(?::[0-9]{1,5})?(?:/\S*)?)"
)
_FINDING_IPV4 = re.compile(r"(?<![0-9])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9])")
_FINDING_IPV6 = re.compile(r"(?i)(?<![0-9a-f:])(?:[0-9a-f]{0,4}:){2,7}[0-9a-f]{0,4}(?![0-9a-f:])")
_FINDING_HOST_PORT = re.compile(
    r"(?i)\b(?:localhost|[a-z0-9][a-z0-9.-]{0,252}):[0-9]{1,5}\b"
)
_FINDING_SECRET_VALUE = re.compile(
    r"(?i)\b(?:(?:sk|rk|pk)-[a-z0-9_-]{12,}|(?:api[-_ ]?)?key\s*[:=]\s*\S+)"
)
_FINDING_OPAQUE = re.compile(
    r"(?i)(?:\b[0-9a-f]{16,}\b|\beyJ[a-z0-9_-]{8,}(?:\.[a-z0-9_-]{8,}){1,2}\b|"
    r"\b[a-z]{24,}\b|"
    r"\b(?=[a-z0-9_-]{24,}\b)(?=[a-z0-9_-]*[0-9_-])[a-z0-9_-]+\b|"
    r"\b[a-z0-9+/]{20,}={1,2})"
)


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _bounded_text(value, name: str, *, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ValueError(f"trusted {name} must be bounded and nonempty")
    return value


class FindingDisposition(str, Enum):
    SAVED = "saved"
    DUPLICATE = "duplicate"
    REJECTED = "rejected"


class FindingKind(str, Enum):
    OBSERVED = "observed"
    HYPOTHESIS = "hypothesis"
    FAILED_METHOD = "failed_method"
    NEXT_STEP = "next_step"


@dataclass(frozen=True)
class Finding:
    """Bounded semantic progress safe to persist for one trusted scope."""

    kind: FindingKind
    summary: str

    def __post_init__(self) -> None:
        value = self.summary
        if (
            not isinstance(self.kind, FindingKind)
            or not isinstance(value, str)
            or not value
            or value != value.strip()
            or len(value.encode("utf-8")) > MAX_FINDING_BYTES
            or any(ord(character) < 32 or ord(character) == 127 for character in value)
            or _FINDING_DENIED_TERMS.search(value)
            or _FINDING_FLAG.search(value)
            or _FINDING_URL.search(value)
            or _FINDING_IPV4.search(value)
            or _FINDING_IPV6.search(value)
            or _FINDING_HOST_PORT.search(value)
            or _FINDING_SECRET_VALUE.search(value)
            or _FINDING_OPAQUE.search(value)
        ):
            raise ValueError("finding must be bounded semantic progress without sensitive data")

    def contains_redaction_value(self, values: Sequence[str]) -> bool:
        summary = self.summary.casefold()
        summary_terms = {
            term.casefold() for term in re.findall(r"[A-Za-z0-9]+", self.summary)
        }
        for value in values:
            if not isinstance(value, str) or not value:
                continue
            folded = value.casefold()
            if folded in summary:
                return True
            if any(
                term.casefold() in summary_terms
                for term in re.findall(r"[A-Za-z0-9]+", value)
            ):
                return True
        return False


def _connection_redaction_values(connection: str) -> tuple[str, ...]:
    return (connection,)


def _runtime_redaction_values() -> tuple[str, ...]:
    return tuple(
        value
        for name in _RUNTIME_REDACTION_ENV
        if isinstance((value := os.environ.get(name)), str) and value
    )


@dataclass(frozen=True)
class AttemptContext:
    challenge_id: int
    category: str
    name: str
    points: int
    challenge_type: str
    material_ref: str
    attempt_id: str
    deadline_monotonic: float
    prior_attempts: int = 0
    instance_generation: str | None = None
    file_count: int = 0
    redaction_values: tuple[str, ...] = field(default=(), repr=False, compare=False)

    def __post_init__(self) -> None:
        if type(self.challenge_id) is not int or self.challenge_id <= 0:
            raise ValueError("trusted challenge ID must be positive")
        if type(self.points) is not int or self.points < 0:
            raise ValueError("trusted points must be nonnegative")
        if type(self.prior_attempts) is not int or not 0 <= self.prior_attempts <= 1_000_000:
            raise ValueError("trusted prior attempts are invalid")
        for name in ("category", "name", "challenge_type", "material_ref", "attempt_id"):
            _bounded_text(getattr(self, name), name)
        if self.instance_generation is not None:
            _bounded_text(self.instance_generation, "instance generation")
        if not isinstance(self.deadline_monotonic, (int, float)) or not math.isfinite(
            self.deadline_monotonic
        ):
            raise ValueError("trusted attempt deadline must be finite")
        if type(self.file_count) is not int or not 0 <= self.file_count <= _MAX_FILES:
            raise ValueError("trusted file count is invalid")
        if (
            not isinstance(self.redaction_values, tuple)
            or len(self.redaction_values) > 64
            or any(
                not isinstance(value, str) or not value
                for value in self.redaction_values
            )
        ):
            raise ValueError("trusted redaction values are invalid")

    def call_id(self, sequence: int) -> str:
        if type(sequence) is not int or sequence <= 0:
            raise ValueError("model sequence must be positive")
        return f"{self.attempt_id}:model:{sequence}"

    def public_prompt(self) -> str:
        category = normalize_category(self.category)
        return (
            f"Trusted scope: challenge {self.challenge_id}; category {category}; "
            f"points {self.points}. "
            "Only supplied files and the inherited live-instance connection are authorized."
        )


def current_attempt(*, required: bool = False) -> AttemptContext | None:
    value = _CURRENT.get()
    if required and value is None:
        raise RuntimeError("trusted attempt context is not bound")
    return value


def _initial_context(challenge: Mapping) -> AttemptContext:
    if not isinstance(challenge, Mapping):
        raise ValueError("trusted challenge must be an object")
    challenge_id = challenge.get("id")
    points = challenge.get("value", challenge.get("points", 0))
    if type(challenge_id) is not int or challenge_id <= 0:
        raise ValueError("trusted challenge ID must be positive")
    if type(points) is not int or points < 0:
        raise ValueError("trusted challenge points must be nonnegative")
    category = _bounded_text(challenge.get("category"), "category")
    name = _bounded_text(challenge.get("name"), "name")
    challenge_type = _bounded_text(challenge.get("type"), "type")
    file_refs = challenge.get("files") or []
    if not isinstance(file_refs, Sequence) or isinstance(file_refs, (str, bytes)):
        raise ValueError("trusted challenge files must be a sequence")
    canonical = json.dumps(
        {
            "id": challenge_id,
            "category": category,
            "name": name,
            "points": points,
            "type": challenge_type,
            "files": [str(item)[:4096] for item in file_refs[:_MAX_FILES]],
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return AttemptContext(
        challenge_id=challenge_id,
        category=category,
        name=name,
        points=points,
        challenge_type=challenge_type,
        material_ref=_digest(canonical),
        attempt_id=uuid.uuid4().hex,
        deadline_monotonic=time.monotonic()
        + min(1800.0, max(60.0, float(os.environ.get("ATTEMPT_TIMEOUT_SECONDS", "480")))),
        redaction_values=_runtime_redaction_values(),
    )


@contextmanager
def trusted_attempt(
    challenge: Mapping, *, deadline_monotonic: float | None = None,
    prior_attempts: int = 0,
) -> Iterator[AttemptContext]:
    """Bind one context from trusted harness metadata and restore it afterward."""
    if _CURRENT.get() is not None:
        raise RuntimeError("nested trusted attempt context")
    context = _initial_context(challenge)
    context = replace(context, prior_attempts=prior_attempts)
    if deadline_monotonic is not None:
        if (
            isinstance(deadline_monotonic, bool)
            or not isinstance(deadline_monotonic, (int, float))
            or not math.isfinite(deadline_monotonic)
        ):
            raise ValueError("trusted outer deadline must be finite")
        context = replace(
            context,
            deadline_monotonic=min(
                context.deadline_monotonic, float(deadline_monotonic)
            ),
        )
    token = _CURRENT.set(context)
    try:
        yield context
    finally:
        _CURRENT.reset(token)


def _hash_file(path: Path) -> tuple[str, int]:
    size = path.stat().st_size
    if size > _MAX_HASH_BYTES:
        raise ValueError("trusted material file exceeds hash limit")
    digest = hashlib.sha256()
    consumed = 0
    with path.open("rb") as stream:
        while True:
            chunk = stream.read(65536)
            if not chunk:
                break
            digest.update(chunk)
            consumed += len(chunk)
            if consumed > _MAX_HASH_BYTES:
                raise ValueError("trusted material file exceeds hash limit")
    if consumed != size:
        raise OSError("trusted material changed while hashing")
    return digest.hexdigest(), consumed


def bind_prepared_material(
    challenge: Mapping,
    directory: str,
    filenames: Sequence[str],
    connection: str | None,
) -> AttemptContext:
    """Enrich the active scope from inherited, trusted prompt-builder arguments."""
    current = current_attempt(required=True)
    assert current is not None
    if challenge.get("id") != current.challenge_id:
        raise RuntimeError("trusted challenge identity changed during preparation")
    root = Path(_bounded_text(directory, "material directory", maximum=8192)).resolve()
    records = []
    for filename in list(filenames)[:_MAX_FILES]:
        if not isinstance(filename, str) or not filename or len(filename) > 4096:
            continue
        candidate = (root / os.path.basename(filename.split(" (download failed:", 1)[0])).resolve()
        if root not in candidate.parents or not candidate.is_file():
            records.append((os.path.basename(filename), "unavailable"))
            continue
        try:
            digest, size = _hash_file(candidate)
        except OSError:
            records.append((candidate.name, "unavailable"))
        else:
            records.append((candidate.name, digest, size))
    material = _digest(
        json.dumps(
            {"prior": current.material_ref, "files": records},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    )
    instance = None
    if connection is not None:
        if not isinstance(connection, str) or not connection or len(connection) > 16384:
            raise ValueError("trusted connection must be bounded")
        instance = _digest(connection.encode())
    elif str(challenge.get("type", "")).lower() in DYNAMIC_CHALLENGE_TYPES:
        # Failed/unavailable instances never share evidence across attempts.
        instance = _digest(("unavailable:" + current.attempt_id).encode())
    enriched = replace(
        current,
        material_ref=material,
        instance_generation=instance,
        file_count=len(records),
        redaction_values=(
            tuple(dict.fromkeys(
                current.redaction_values
                + (_connection_redaction_values(connection) if connection is not None else ())
            ))[:64]
        ),
    )
    _CURRENT.set(enriched)
    return enriched
