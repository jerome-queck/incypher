"""Bounded restart-safe coordinator state.

Only trusted identifiers, hashes, enums, counts, timestamps, fingerprints and
sanitized summaries are persisted.  Raw commands and command output are hashed
in memory and are never written to SQLite.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import threading
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from contextlib import closing
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .runtime_context import DYNAMIC_CHALLENGE_TYPES


MAX_PROJECTION_RECORDS = 16
MAX_PROJECTION_BYTES = 8 * 1024
MAX_SUMMARY_BYTES = 512
MAX_SCOPE_OBSERVATIONS = 256
MAX_TOTAL_OBSERVATIONS = 4096
_MAX_CHALLENGES = 4096
_HASH_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")
_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(?:flag|ctf)\{[^\r\n}]{1,512}\}"),
    re.compile(r"(?i)\b(?:api[_-]?key|token|password|secret)\s*[:=]\s*[^\s,;]{3,512}"),
    re.compile(r"(?i)\b(?:https?|ssh|tcp)://[^\s]{1,1024}"),
    re.compile(r"\b(?:sk|rk|pk)-[A-Za-z0-9_-]{12,}\b"),
)


class RuntimeStateError(RuntimeError):
    """Bounded, payload-free persistent-state failure."""


class ChallengeKind(str, Enum):
    STATIC = "static"
    DYNAMIC = "dynamic"


class AttemptOutcome(str, Enum):
    UNSOLVED = "unsolved"
    SOLVED = "solved"
    TIMEOUT = "timeout"
    RESOURCE = "resource"
    PROVIDER = "provider"
    SUBMISSION = "submission"
    CANCELLED = "cancelled"
    CRASH = "crash"


class ObservationKind(str, Enum):
    COMMAND = "command"
    MODEL = "model"
    TOOL = "tool"
    FINDING = "finding"
    REPLAN = "replan"


def _identifier(value: str, name: str) -> str:
    if not isinstance(value, str) or not _HASH_RE.fullmatch(value):
        raise ValueError(f"{name} must be a bounded trusted identifier or hash")
    return value


def _challenge_id(value: int) -> int:
    if type(value) is not int or value < 0:
        raise ValueError("challenge_id must be a nonnegative integer")
    return value


@dataclass(frozen=True)
class Scope:
    challenge_id: int
    material_hash: str
    kind: ChallengeKind
    instance_hash: str | None = None

    def __post_init__(self) -> None:
        _challenge_id(self.challenge_id)
        _identifier(self.material_hash, "material_hash")
        if not isinstance(self.kind, ChallengeKind):
            raise ValueError("typed challenge kind required")
        if self.kind is ChallengeKind.DYNAMIC:
            if self.instance_hash is None:
                raise ValueError("dynamic scope requires instance_hash")
            _identifier(self.instance_hash, "instance_hash")
        elif self.instance_hash is not None:
            raise ValueError("static scope must not have instance_hash")

    @property
    def key(self) -> str:
        payload = json.dumps(
            [self.challenge_id, self.material_hash, self.kind.value, self.instance_hash],
            separators=(",", ":"),
        ).encode("ascii")
        return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class ChallengeBrief:
    challenge_id: int
    points: int
    kind: ChallengeKind
    material_hash: str
    instance_hash: str | None = None
    solved: bool = False

    def __post_init__(self) -> None:
        _challenge_id(self.challenge_id)
        if type(self.points) is not int or self.points < 0:
            raise ValueError("points must be a nonnegative integer")
        if type(self.solved) is not bool:
            raise ValueError("solved must be boolean")
        Scope(self.challenge_id, self.material_hash, self.kind, self.instance_hash)

    @property
    def scope(self) -> Scope:
        return Scope(self.challenge_id, self.material_hash, self.kind, self.instance_hash)


@dataclass(frozen=True)
class RankedChallenge:
    brief: ChallengeBrief
    eligible: bool
    attempts: int
    progress: int
    backoff_seconds: float


@dataclass(frozen=True)
class Projection:
    text: str
    record_count: int

    @property
    def byte_count(self) -> int:
        return len(self.text.encode("utf-8"))


def command_fingerprint(scope: Scope, command: str) -> str:
    """Return a scoped fingerprint without retaining the raw command."""
    if not isinstance(scope, Scope):
        raise ValueError("Scope required")
    if (
        not isinstance(command, str)
        or not command
        or len(command.encode("utf-8")) > 64 * 1024
    ):
        raise ValueError("command must be nonempty and bounded")
    return hashlib.sha256((scope.key + "\0" + command).encode("utf-8")).hexdigest()


def _field(value: object, name: str, default: object = None) -> object:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def scope_from_context(context: object) -> Scope:
    """Convert the trusted runtime context without retaining connection data."""
    challenge_id = _field(context, "challenge_id", _field(context, "id"))
    material = _field(context, "material_ref", _field(context, "material_hash"))
    instance = _field(
        context, "instance_generation", _field(context, "instance_hash")
    )
    challenge_type = str(
        _field(context, "challenge_type", _field(context, "type", ""))
    ).lower()
    dynamic = instance is not None or challenge_type in DYNAMIC_CHALLENGE_TYPES
    return Scope(
        challenge_id,
        material,
        ChallengeKind.DYNAMIC if dynamic else ChallengeKind.STATIC,
        instance if dynamic else None,
    )


def scope_key(context: object) -> str:
    """Return the stable challenge/material/instance key for trusted context."""
    return scope_from_context(context).key


def _fingerprint(value: str | bytes) -> str:
    if isinstance(value, str):
        value = value.encode("utf-8", "replace")
    if not isinstance(value, bytes):
        raise ValueError("fingerprinted value must be str or bytes")
    return hashlib.sha256(value).hexdigest()


def _sanitize(summary: str, sensitive_values: Iterable[str] = ()) -> str:
    if not isinstance(summary, str):
        raise ValueError("summary must be text")
    # Bound work before regex processing and remove terminal/control sequences.
    text = summary[:4096].replace("\x1b", "?")
    text = "".join(ch if ch in "\t " or ord(ch) >= 32 else " " for ch in text)
    for value in sensitive_values:
        if isinstance(value, str) and len(value) >= 3 and len(value) <= 4096:
            text = text.replace(value, "[redacted]")
            # A summary commonly names just the interesting command/output
            # token. Remove distinctive fragments too, without retaining them.
            for fragment in re.findall(r"[A-Za-z0-9_{}:/?=@.-]{8,}", value):
                text = text.replace(fragment, "[redacted]")
            for fragment in re.findall(r"[A-Za-z0-9_{}.-]{8,}", value):
                text = text.replace(fragment, "[redacted]")
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub("[redacted]", text)
    text = " ".join(text.split()) or "[empty]"
    encoded = text.encode("utf-8")
    if len(encoded) > MAX_SUMMARY_BYTES:
        text = encoded[: MAX_SUMMARY_BYTES - 3].decode("utf-8", "ignore") + "..."
    return text


class RuntimeState:
    """Dependency-free SQLite state with short, atomic operations.

    ``before_commit`` is a test seam invoked inside write transactions.  A
    raised exception rolls the entire operation back.
    """

    def __init__(
        self,
        path: str | os.PathLike[str] = "/work/runtime-state.sqlite3",
        *,
        timeout: float = 0.25,
        before_commit: Callable[[str], None] | None = None,
    ):
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool):
            raise ValueError("timeout must be numeric")
        if not math.isfinite(timeout) or timeout < 0 or timeout > 5:
            raise ValueError("timeout must be between zero and five seconds")
        self.path = Path(path)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise RuntimeStateError("runtime state is unavailable") from exc
        self.timeout = float(timeout)
        self.before_commit = before_commit
        self._initialise_lock = threading.Lock()
        self._rank_scopes: dict[int, Scope] = {}
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=self.timeout, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {int(self.timeout * 1000)}")
        return connection

    def _initialise(self) -> None:
        try:
            with self._initialise_lock, closing(self._connect()) as connection:
                connection.execute("PRAGMA journal_mode = WAL")
                connection.execute("PRAGMA synchronous = FULL")
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS challenge_state (
                        scope_key TEXT PRIMARY KEY,
                        challenge_id INTEGER NOT NULL,
                        material_hash TEXT NOT NULL,
                        challenge_kind TEXT NOT NULL,
                        instance_hash TEXT,
                        attempts INTEGER NOT NULL,
                        progress INTEGER NOT NULL,
                        failure_streak INTEGER NOT NULL,
                        last_outcome TEXT NOT NULL,
                        solved INTEGER NOT NULL,
                        backoff_until REAL NOT NULL,
                        last_attempt_at REAL NOT NULL,
                        updated_at REAL NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS observations (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        scope_key TEXT NOT NULL,
                        challenge_id INTEGER NOT NULL,
                        material_hash TEXT NOT NULL,
                        challenge_kind TEXT NOT NULL,
                        instance_hash TEXT,
                        observation_kind TEXT NOT NULL,
                        command_fp TEXT,
                        output_fp TEXT,
                        summary TEXT NOT NULL,
                        progress INTEGER NOT NULL,
                        created_at REAL NOT NULL
                    );
                    CREATE UNIQUE INDEX IF NOT EXISTS observations_command_dedupe
                        ON observations(scope_key, command_fp) WHERE command_fp IS NOT NULL;
                    CREATE INDEX IF NOT EXISTS observations_scope_time
                        ON observations(scope_key, created_at DESC, id DESC);
                    """
                )
        except (OSError, sqlite3.Error) as exc:
            raise RuntimeStateError("runtime state is unavailable") from exc

    @staticmethod
    def _begin(connection: sqlite3.Connection) -> None:
        connection.execute("BEGIN IMMEDIATE")

    def _commit(self, connection: sqlite3.Connection, operation: str) -> None:
        try:
            if self.before_commit is not None:
                self.before_commit(operation)
            connection.execute("COMMIT")
        except Exception as exc:
            try:
                connection.execute("ROLLBACK")
            except sqlite3.Error:
                pass
            raise RuntimeStateError(f"{operation} was not committed") from exc

    @staticmethod
    def _rollback(connection: sqlite3.Connection) -> None:
        try:
            connection.execute("ROLLBACK")
        except sqlite3.Error:
            pass

    @staticmethod
    def _valid_state_row(row: sqlite3.Row, scope: Scope) -> bool:
        try:
            return (
                row["scope_key"] == scope.key
                and row["challenge_id"] == scope.challenge_id
                and row["material_hash"] == scope.material_hash
                and row["challenge_kind"] == scope.kind.value
                and row["instance_hash"] == scope.instance_hash
                and type(row["attempts"]) is int
                and 0 <= row["attempts"] <= 1_000_000
                and type(row["progress"]) is int
                and 0 <= row["progress"] <= 1_000_000
                and type(row["failure_streak"]) is int
                and 0 <= row["failure_streak"] <= 1_000_000
                and AttemptOutcome(row["last_outcome"])
                and row["solved"] in (0, 1)
                and math.isfinite(float(row["backoff_until"]))
                and math.isfinite(float(row["last_attempt_at"]))
            )
        except (KeyError, TypeError, ValueError, OverflowError):
            return False

    def rank(
        self, briefs: Sequence[ChallengeBrief], *, now: float | None = None
    ) -> tuple[RankedChallenge, ...]:
        """Rank trusted briefs without changing their numeric identifiers."""
        if not isinstance(briefs, Sequence) or isinstance(briefs, (str, bytes)):
            raise ValueError("briefs must be a sequence")
        if len(briefs) > _MAX_CHALLENGES:
            raise ValueError("too many challenge briefs")
        if any(not isinstance(item, ChallengeBrief) for item in briefs):
            raise ValueError("typed challenge briefs required")
        identifiers = [item.challenge_id for item in briefs]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("duplicate numeric challenge ID")
        instant = time.time() if now is None else float(now)
        if not math.isfinite(instant):
            raise ValueError("now must be finite")
        keys = [item.scope.key for item in briefs]
        rows: dict[str, sqlite3.Row] = {}
        try:
            with closing(self._connect()) as connection:
                # Avoid an unbounded SQL expression while retaining one read snapshot.
                for offset in range(0, len(keys), 400):
                    batch = keys[offset : offset + 400]
                    if not batch:
                        continue
                    placeholders = ",".join("?" for _ in batch)
                    for row in connection.execute(
                        f"SELECT * FROM challenge_state WHERE scope_key IN ({placeholders})",
                        batch,
                    ):
                        rows[row["scope_key"]] = row
        except sqlite3.Error as exc:
            raise RuntimeStateError("runtime state read failed") from exc

        ranked: list[tuple[tuple[object, ...], RankedChallenge]] = []
        for brief in briefs:
            row = rows.get(brief.scope.key)
            if row is None or not self._valid_state_row(row, brief.scope):
                attempts = progress = 0
                backoff_until = last_attempt = 0.0
                locally_solved = False
            else:
                attempts, progress = row["attempts"], row["progress"]
                backoff_until = float(row["backoff_until"])
                last_attempt = float(row["last_attempt_at"])
                locally_solved = bool(row["solved"])
            solved = brief.solved or locally_solved
            eligible = backoff_until <= instant
            remaining = max(0.0, backoff_until - instant)
            item = RankedChallenge(brief, eligible, attempts, progress, remaining)
            # Saved only for the deterministic sort below.
            item_key = (
                solved,
                not eligible,
                -brief.points,
                -progress,
                attempts,
                brief.kind is ChallengeKind.DYNAMIC,
                last_attempt,
                brief.challenge_id,
            )
            ranked.append((item_key, item))
        ranked.sort(key=lambda pair: pair[0])
        return tuple(pair[1] for pair in ranked)

    @staticmethod
    def _brief_adapter(brief: object) -> ChallengeBrief:
        challenge_id = _field(brief, "id", _field(brief, "challenge_id"))
        points = _field(brief, "value", _field(brief, "points", 0))
        solved = _field(brief, "solved", False)
        challenge_type = str(
            _field(brief, "type", _field(brief, "challenge_type", ""))
        ).lower()
        explicit_dynamic = _field(
            brief, "is_dynamic", _field(brief, "dynamic", False)
        )
        kind = (
            ChallengeKind.DYNAMIC
            if explicit_dynamic is True
            or challenge_type in DYNAMIC_CHALLENGE_TYPES
            else ChallengeKind.STATIC
        )
        # Ranking happens before prepared files/instances exist. This trusted
        # digest is ranking provenance only; evidence projection uses AttemptContext.
        material = hashlib.sha256(
            json.dumps(
                [challenge_id, points, challenge_type], separators=(",", ":"),
                ensure_ascii=True,
            ).encode("ascii")
        ).hexdigest()
        instance = "pending" if kind is ChallengeKind.DYNAMIC else None
        return ChallengeBrief(challenge_id, points, kind, material, instance, solved)

    def rank_briefs(
        self, briefs: Sequence[object], now: float | None = None
    ) -> list[object]:
        """Rank inherited trusted brief objects and return those same objects."""
        adapted = [self._brief_adapter(brief) for brief in briefs]
        self._rank_scopes = {brief.challenge_id: brief.scope for brief in adapted}
        by_id = {brief.challenge_id: original for brief, original in zip(adapted, briefs)}
        return [by_id[item.brief.challenge_id] for item in self.rank(adapted, now=now)]

    def record_challenge_outcome(
        self,
        challenge_id: int,
        solved: bool,
        progress: int,
        failure_class: AttemptOutcome | str,
        now: float | None = None,
    ) -> RankedChallenge:
        """Checkpoint the outcome for a brief most recently admitted to ranking."""
        _challenge_id(challenge_id)
        if type(solved) is not bool:
            raise ValueError("solved must be boolean")
        if type(progress) is not int or not 0 <= progress <= 1_000_000:
            raise ValueError("progress must be a bounded nonnegative integer")
        scope = self._rank_scopes.get(challenge_id)
        if scope is None:
            raise RuntimeStateError("challenge was not present in the trusted brief list")
        try:
            outcome = AttemptOutcome.SOLVED if solved else AttemptOutcome(failure_class)
        except (TypeError, ValueError):
            raise ValueError("unsupported failure_class") from None
        return self.checkpoint_outcome(
            scope, outcome, progress_total=progress, now=now
        )

    def checkpoint_outcome(
        self,
        scope: Scope,
        outcome: AttemptOutcome,
        *,
        progress_delta: int = 0,
        progress_total: int | None = None,
        now: float | None = None,
    ) -> RankedChallenge:
        if not isinstance(scope, Scope) or not isinstance(outcome, AttemptOutcome):
            raise ValueError("typed scope and outcome required")
        if type(progress_delta) is not int or not 0 <= progress_delta <= 1_000_000:
            raise ValueError("progress_delta must be a bounded nonnegative integer")
        if progress_total is not None and (
            type(progress_total) is not int or not 0 <= progress_total <= 1_000_000
        ):
            raise ValueError("progress_total must be a bounded nonnegative integer")
        instant = time.time() if now is None else float(now)
        if not math.isfinite(instant):
            raise ValueError("now must be finite")
        try:
            with closing(self._connect()) as connection:
                self._begin(connection)
                row = connection.execute(
                    "SELECT * FROM challenge_state WHERE scope_key = ?", (scope.key,)
                ).fetchone()
                valid = row is not None and self._valid_state_row(row, scope)
                attempts = min((row["attempts"] if valid else 0) + 1, 1_000_000)
                prior_progress = row["progress"] if valid else 0
                progress = (
                    max(prior_progress, progress_total)
                    if progress_total is not None
                    else min(prior_progress + progress_delta, 1_000_000)
                )
                solved = outcome is AttemptOutcome.SOLVED or bool(row["solved"] if valid else 0)
                streak = (
                    0
                    if solved
                    else min((row["failure_streak"] if valid else 0) + 1, 1_000_000)
                )
                delay = 0.0 if solved else float(min(streak, 2))
                connection.execute(
                    """
                    INSERT OR REPLACE INTO challenge_state(
                        scope_key, challenge_id, material_hash, challenge_kind,
                        instance_hash, attempts, progress, failure_streak,
                        last_outcome, solved, backoff_until, last_attempt_at, updated_at
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        scope.key, scope.challenge_id, scope.material_hash, scope.kind.value,
                        scope.instance_hash, attempts, progress, streak, outcome.value,
                        int(solved), instant + delay, instant, instant,
                    ),
                )
                connection.execute(
                    """DELETE FROM challenge_state WHERE scope_key NOT IN
                       (SELECT scope_key FROM challenge_state
                        ORDER BY updated_at DESC, scope_key DESC LIMIT ?)""",
                    (_MAX_CHALLENGES,),
                )
                self._commit(connection, "checkpoint_outcome")
        except RuntimeStateError:
            raise
        except sqlite3.Error as exc:
            raise RuntimeStateError("checkpoint_outcome failed") from exc
        brief = ChallengeBrief(
            scope.challenge_id, 0, scope.kind, scope.material_hash, scope.instance_hash, solved
        )
        return RankedChallenge(brief, solved or delay == 0, attempts, progress, delay)

    def command_seen(self, scope: Scope, command: str) -> bool:
        fingerprint = command_fingerprint(scope, command)
        try:
            with closing(self._connect()) as connection:
                row = connection.execute(
                    "SELECT 1 FROM observations WHERE scope_key = ? AND command_fp = ?",
                    (scope.key, fingerprint),
                ).fetchone()
                return row is not None
        except sqlite3.Error as exc:
            raise RuntimeStateError("command dedupe read failed") from exc

    def lookup_command(self, context: Scope | object, command: str) -> bool:
        """Integration alias accepting either Scope or trusted AttemptContext."""
        scope = context if isinstance(context, Scope) else scope_from_context(context)
        return self.command_seen(scope, command)

    def lookup(self, context: Scope | object, command: str) -> bool:
        """Return whether an exact command already ran in this current scope."""
        return self.lookup_command(context, command)

    def record_command(
        self,
        scope: Scope,
        command: str,
        output: str | bytes,
        summary: str,
        *,
        progress: int = 0,
        sensitive_values: Iterable[str] = (),
        now: float | None = None,
    ) -> bool:
        """Record command evidence; return False for an exact scoped duplicate."""
        command_fp = command_fingerprint(scope, command)
        output_fp = _fingerprint(output)
        automatic = [command]
        if isinstance(output, str) and len(output) <= 4096:
            automatic.append(output)
        return self._record_observation(
            scope, ObservationKind.COMMAND, summary, command_fp=command_fp,
            output_fp=output_fp, progress=progress,
            sensitive_values=(*automatic, *tuple(sensitive_values)), now=now,
        )

    def record(
        self,
        context: Scope | object,
        command: str,
        output: str | bytes,
        summary: str,
        **kwargs: object,
    ) -> bool:
        """Integration alias for recording one scoped command outcome."""
        scope = context if isinstance(context, Scope) else scope_from_context(context)
        return self.record_command(scope, command, output, summary, **kwargs)

    def record_observation(
        self,
        scope: Scope,
        kind: ObservationKind,
        summary: str,
        *,
        progress: int = 0,
        sensitive_values: Iterable[str] = (),
        now: float | None = None,
    ) -> bool:
        return self._record_observation(
            scope, kind, summary, progress=progress,
            sensitive_values=sensitive_values, now=now,
        )

    def _record_observation(
        self,
        scope: Scope,
        kind: ObservationKind,
        summary: str,
        *,
        command_fp: str | None = None,
        output_fp: str | None = None,
        progress: int = 0,
        sensitive_values: Iterable[str] = (),
        now: float | None = None,
    ) -> bool:
        if not isinstance(scope, Scope) or not isinstance(kind, ObservationKind):
            raise ValueError("typed scope and observation kind required")
        if type(progress) is not int or not 0 <= progress <= 1_000_000:
            raise ValueError("progress must be a bounded nonnegative integer")
        clean = _sanitize(summary, sensitive_values)
        instant = time.time() if now is None else float(now)
        if not math.isfinite(instant):
            raise ValueError("now must be finite")
        try:
            with closing(self._connect()) as connection:
                self._begin(connection)
                try:
                    connection.execute(
                        """
                        INSERT INTO observations(
                            scope_key, challenge_id, material_hash, challenge_kind,
                            instance_hash, observation_kind, command_fp, output_fp,
                            summary, progress, created_at
                        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            scope.key, scope.challenge_id, scope.material_hash, scope.kind.value,
                            scope.instance_hash, kind.value, command_fp, output_fp, clean,
                            progress, instant,
                        ),
                    )
                except sqlite3.IntegrityError:
                    self._rollback(connection)
                    return False
                connection.execute(
                    """DELETE FROM observations WHERE scope_key = ? AND id NOT IN
                       (SELECT id FROM observations WHERE scope_key = ?
                        ORDER BY created_at DESC, id DESC LIMIT ?)""",
                    (scope.key, scope.key, MAX_SCOPE_OBSERVATIONS),
                )
                connection.execute(
                    """DELETE FROM observations WHERE id NOT IN
                       (SELECT id FROM observations ORDER BY created_at DESC, id DESC LIMIT ?)""",
                    (MAX_TOTAL_OBSERVATIONS,),
                )
                self._commit(connection, "record_observation")
                return True
        except RuntimeStateError:
            raise
        except sqlite3.Error as exc:
            raise RuntimeStateError("record_observation failed") from exc

    @staticmethod
    def _valid_observation(row: sqlite3.Row, scope: Scope) -> bool:
        try:
            summary = row["summary"]
            return (
                row["scope_key"] == scope.key
                and row["challenge_id"] == scope.challenge_id
                and row["material_hash"] == scope.material_hash
                and row["challenge_kind"] == scope.kind.value
                and row["instance_hash"] == scope.instance_hash
                and ObservationKind(row["observation_kind"])
                and isinstance(summary, str)
                and 0 < len(summary.encode("utf-8")) <= MAX_SUMMARY_BYTES
                and type(row["progress"]) is int
                and 0 <= row["progress"] <= 1_000_000
                and math.isfinite(float(row["created_at"]))
                and (row["command_fp"] is None or re.fullmatch(r"[0-9a-f]{64}", row["command_fp"]))
                and (row["output_fp"] is None or re.fullmatch(r"[0-9a-f]{64}", row["output_fp"]))
            )
        except (KeyError, TypeError, ValueError, OverflowError):
            return False

    def project(self, scope: Scope | object) -> Projection:
        """Return newest applicable records, capped at 16 records and 8 KiB."""
        scope = scope if isinstance(scope, Scope) else scope_from_context(scope)
        try:
            with closing(self._connect()) as connection:
                rows = connection.execute(
                    """SELECT * FROM observations WHERE scope_key = ?
                       ORDER BY created_at DESC, id DESC LIMIT ?""",
                    (scope.key, MAX_SCOPE_OBSERVATIONS),
                ).fetchall()
        except sqlite3.Error as exc:
            raise RuntimeStateError("memory projection read failed") from exc
        lines: list[str] = []
        size = 0
        for row in rows:
            if len(lines) >= MAX_PROJECTION_RECORDS or not self._valid_observation(row, scope):
                continue
            record = json.dumps(
                {
                    "kind": row["observation_kind"],
                    "summary": row["summary"],
                    "progress": row["progress"],
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            encoded = record.encode("utf-8")
            separator = 1 if lines else 0
            if size + separator + len(encoded) > MAX_PROJECTION_BYTES:
                continue
            lines.append(record)
            size += separator + len(encoded)
        return Projection("\n".join(lines), len(lines))

    def project_memory(self, context: Scope | object) -> Projection:
        """Integration alias accepting either Scope or trusted AttemptContext."""
        scope = context if isinstance(context, Scope) else scope_from_context(context)
        return self.project(scope)

    def checkpoint(self) -> None:
        """Request a bounded WAL checkpoint; readers remain safe during writes."""
        try:
            with closing(self._connect()) as connection:
                connection.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
        except sqlite3.Error as exc:
            raise RuntimeStateError("runtime state checkpoint failed") from exc
