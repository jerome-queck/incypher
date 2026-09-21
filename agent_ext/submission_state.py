"""Durable private candidate deduplication and submission-intent state.

The store never sends a candidate and never interprets raw HTTP responses.  The
integration owner must durably mark ``dispatch_possible`` immediately before the
single trusted callback can be invoked, then apply a classified adapter event.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .memory import EvidenceScope
from .verification import DuplicateDisposition


class IntentState(str, Enum):
    RESERVED = "reserved"
    PROVEN_NOT_SENT = "proven_not_sent"
    DISPATCH_POSSIBLE = "dispatch_possible"
    UNKNOWN = "unknown"
    WRONG = "wrong"
    ACCEPTED = "accepted"
    RECONCILE = "reconcile"
    CONFLICT = "conflict"


class AdapterOutcome(str, Enum):
    ACCEPTED = "accepted"
    WRONG = "wrong"
    ACCOUNT_ALREADY_SOLVED = "account_already_solved"
    UNKNOWN = "unknown"
    RATE_LIMITED = "rate_limited"
    AUTHENTICATION_FAILED = "authentication_failed"
    MALFORMED_RESPONSE = "malformed_response"
    CANCELLED = "cancelled"


class RecoveryDisposition(str, Enum):
    NO_INTENT = "no_intent"
    PROVEN_NOT_SENT = "proven_not_sent"
    RECONCILE = "reconcile"
    SETTLED = "settled"


class StorageCommitError(RuntimeError):
    pass


class StoragePressure(RuntimeError):
    pass


@dataclass(frozen=True)
class Reservation:
    intent_id: str
    candidate_id: str
    created: bool
    dispatch_allowed: bool
    reason: str
    state: IntentState


@dataclass(frozen=True)
class OutcomeEvent:
    event_id: str
    outcome: AdapterOutcome
    authoritative: bool
    attributable: bool
    synthetic: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.event_id, str) or not self.event_id or len(self.event_id) > 256:
            raise ValueError("event_id must be bounded and nonempty")
        if not isinstance(self.outcome, AdapterOutcome):
            raise ValueError("typed adapter outcome required")
        for name in ("authoritative", "attributable", "synthetic"):
            if type(getattr(self, name)) is not bool:
                raise ValueError(f"{name} must be boolean")


@dataclass(frozen=True)
class IntentSnapshot:
    intent_id: str
    candidate_id: str
    state: IntentState
    dispatch_possible: bool
    event_count: int
    synthetic_acceptance: bool


def _scope_json(scope: EvidenceScope) -> str:
    if not isinstance(scope, EvidenceScope):
        raise ValueError("EvidenceScope required")
    # attempt_id is provenance, not duplicate identity.  A renamed approach or
    # child attempt therefore cannot reopen the same candidate send.
    return json.dumps(
        {
            "run_id": scope.run_id,
            "phase": scope.phase,
            "challenge_id": scope.challenge_id,
            "material_ref": scope.material_ref,
            "instance_generation": scope.instance_generation,
            "branch_id": scope.branch_id,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


class SubmissionStateStore:
    """A small SQLite ledger for private intents and idempotent outcomes."""

    def __init__(
        self,
        path: str | os.PathLike[str],
        *,
        before_commit: Callable[[str], None] | None = None,
    ):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.before_commit = before_commit
        self._initialise_lock = threading.Lock()
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def _initialise(self) -> None:
        with self._initialise_lock, closing(self._connect()) as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS private_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS submission_intents (
                    intent_id TEXT PRIMARY KEY,
                    candidate_id TEXT NOT NULL,
                    scope_json TEXT NOT NULL,
                    duplicate_key TEXT NOT NULL UNIQUE,
                    state TEXT NOT NULL,
                    dispatch_possible INTEGER NOT NULL DEFAULT 0,
                    synthetic_acceptance INTEGER NOT NULL DEFAULT 0,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS submission_events (
                    event_id TEXT PRIMARY KEY,
                    intent_id TEXT NOT NULL REFERENCES submission_intents(intent_id),
                    outcome TEXT NOT NULL,
                    authoritative INTEGER NOT NULL,
                    attributable INTEGER NOT NULL,
                    synthetic INTEGER NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS submission_events_intent
                    ON submission_events(intent_id);
                """
            )
            row = connection.execute(
                "SELECT value FROM private_meta WHERE key = 'duplicate_secret'"
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO private_meta(key, value) VALUES('duplicate_secret', ?)",
                    (os.urandom(32).hex(),),
                )

    def _secret(self, connection: sqlite3.Connection) -> bytes:
        row = connection.execute(
            "SELECT value FROM private_meta WHERE key = 'duplicate_secret'"
        ).fetchone()
        if row is None:
            raise StorageCommitError("private duplicate secret is unavailable")
        return bytes.fromhex(row["value"])

    def _duplicate_key(
        self, connection: sqlite3.Connection, scope: EvidenceScope, candidate: bytes
    ) -> tuple[str, str]:
        if not isinstance(candidate, bytes) or not candidate or len(candidate) > 4096:
            raise ValueError("candidate must be exact bounded bytes")
        scoped = _scope_json(scope)
        payload = scoped.encode("utf-8") + b"\x00" + candidate
        return scoped, hmac.new(self._secret(connection), payload, hashlib.sha256).hexdigest()

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
            raise StorageCommitError(f"{operation} was not committed") from exc

    @staticmethod
    def _reservation(row: sqlite3.Row, *, created: bool) -> Reservation:
        state = IntentState(row["state"])
        allowed = state in {IntentState.RESERVED, IntentState.PROVEN_NOT_SENT}
        reason = (
            "new_durable_reservation"
            if created
            else "resume_proven_not_sent_intent"
            if allowed
            else f"duplicate_suppressed_{state.value}"
        )
        return Reservation(
            row["intent_id"], row["candidate_id"], created, allowed, reason, state
        )

    def reserve(self, scope: EvidenceScope, candidate: bytes) -> Reservation:
        with closing(self._connect()) as connection:
            try:
                connection.execute("BEGIN IMMEDIATE")
                scoped, duplicate_key = self._duplicate_key(connection, scope, candidate)
                row = connection.execute(
                    "SELECT * FROM submission_intents WHERE duplicate_key = ?",
                    (duplicate_key,),
                ).fetchone()
                if row is not None:
                    connection.execute("COMMIT")
                    return self._reservation(row, created=False)
                now = time.time()
                intent_id = "intent:" + uuid.uuid4().hex
                candidate_id = "opaque:" + uuid.uuid4().hex
                connection.execute(
                    """
                    INSERT INTO submission_intents(
                        intent_id, candidate_id, scope_json, duplicate_key, state,
                        dispatch_possible, created_at, updated_at
                    ) VALUES(?, ?, ?, ?, ?, 0, ?, ?)
                    """,
                    (
                        intent_id,
                        candidate_id,
                        scoped,
                        duplicate_key,
                        IntentState.RESERVED.value,
                        now,
                        now,
                    ),
                )
                self._commit(connection, "reserve")
            except StorageCommitError:
                raise
            except Exception as exc:
                try:
                    connection.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                raise StorageCommitError("reserve was not committed") from exc
        return Reservation(
            intent_id,
            candidate_id,
            True,
            True,
            "new_durable_reservation",
            IntentState.RESERVED,
        )

    def mark_dispatch_possible(self, intent_id: str) -> bool:
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT state FROM submission_intents WHERE intent_id = ?", (intent_id,)
            ).fetchone()
            if row is None:
                connection.execute("ROLLBACK")
                raise KeyError(intent_id)
            state = IntentState(row["state"])
            if state not in {IntentState.RESERVED, IntentState.PROVEN_NOT_SENT}:
                connection.execute("COMMIT")
                return False
            connection.execute(
                """
                UPDATE submission_intents
                SET state = ?, dispatch_possible = 1, updated_at = ?
                WHERE intent_id = ?
                """,
                (IntentState.DISPATCH_POSSIBLE.value, time.time(), intent_id),
            )
            self._commit(connection, "dispatch_possible")
            return True

    def prove_not_sent(self, intent_id: str) -> bool:
        """Record proof that the dispatch boundary was never crossed."""
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT state, dispatch_possible FROM submission_intents WHERE intent_id = ?",
                (intent_id,),
            ).fetchone()
            if row is None:
                connection.execute("ROLLBACK")
                raise KeyError(intent_id)
            if row["dispatch_possible"] or IntentState(row["state"]) not in {
                IntentState.RESERVED,
                IntentState.PROVEN_NOT_SENT,
            }:
                connection.execute("COMMIT")
                return False
            connection.execute(
                "UPDATE submission_intents SET state = ?, updated_at = ? WHERE intent_id = ?",
                (IntentState.PROVEN_NOT_SENT.value, time.time(), intent_id),
            )
            self._commit(connection, "prove_not_sent")
            return True

    def record_outcome(self, intent_id: str, event: OutcomeEvent) -> IntentSnapshot:
        if not isinstance(event, OutcomeEvent):
            raise ValueError("OutcomeEvent required")
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            intent = connection.execute(
                "SELECT * FROM submission_intents WHERE intent_id = ?", (intent_id,)
            ).fetchone()
            if intent is None:
                connection.execute("ROLLBACK")
                raise KeyError(intent_id)
            prior_event = connection.execute(
                "SELECT * FROM submission_events WHERE event_id = ?", (event.event_id,)
            ).fetchone()
            if prior_event is not None:
                same = (
                    prior_event["intent_id"] == intent_id
                    and prior_event["outcome"] == event.outcome.value
                    and bool(prior_event["authoritative"]) == event.authoritative
                    and bool(prior_event["attributable"]) == event.attributable
                    and bool(prior_event["synthetic"]) == event.synthetic
                )
                connection.execute("COMMIT")
                if not same:
                    raise ValueError("event identity replayed with contradictory content")
                return self.snapshot(intent_id)

            current = IntentState(intent["state"])
            definitive_new: IntentState | None = None
            if event.authoritative and event.attributable:
                if event.outcome is AdapterOutcome.ACCEPTED:
                    definitive_new = IntentState.ACCEPTED
                elif event.outcome is AdapterOutcome.WRONG:
                    definitive_new = IntentState.WRONG

            if current is IntentState.CONFLICT:
                new_state = current
            elif definitive_new is not None:
                opposite = {
                    IntentState.ACCEPTED: IntentState.WRONG,
                    IntentState.WRONG: IntentState.ACCEPTED,
                }[definitive_new]
                new_state = IntentState.CONFLICT if current is opposite else definitive_new
            elif current in {IntentState.ACCEPTED, IntentState.WRONG}:
                # Delayed timeout/rate-limit evidence cannot erase an attributable result.
                new_state = current
            elif event.outcome is AdapterOutcome.ACCOUNT_ALREADY_SOLVED:
                new_state = IntentState.RECONCILE
            else:
                new_state = IntentState.UNKNOWN

            connection.execute(
                """
                INSERT INTO submission_events(
                    event_id, intent_id, outcome, authoritative, attributable,
                    synthetic, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    intent_id,
                    event.outcome.value,
                    int(event.authoritative),
                    int(event.attributable),
                    int(event.synthetic),
                    time.time(),
                ),
            )
            synthetic_acceptance = bool(intent["synthetic_acceptance"]) or (
                definitive_new is IntentState.ACCEPTED and event.synthetic
            )
            connection.execute(
                """
                UPDATE submission_intents
                SET state = ?, synthetic_acceptance = ?, updated_at = ?
                WHERE intent_id = ?
                """,
                (new_state.value, int(synthetic_acceptance), time.time(), intent_id),
            )
            self._commit(connection, "record_outcome")
        return self.snapshot(intent_id)

    def snapshot(self, intent_id: str) -> IntentSnapshot:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT i.*, COUNT(e.event_id) AS event_count
                FROM submission_intents i
                LEFT JOIN submission_events e ON e.intent_id = i.intent_id
                WHERE i.intent_id = ?
                GROUP BY i.intent_id
                """,
                (intent_id,),
            ).fetchone()
        if row is None:
            raise KeyError(intent_id)
        return IntentSnapshot(
            row["intent_id"],
            row["candidate_id"],
            IntentState(row["state"]),
            bool(row["dispatch_possible"]),
            row["event_count"],
            bool(row["synthetic_acceptance"]),
        )

    def recover(self, intent_id: str | None) -> RecoveryDisposition:
        if intent_id is None:
            return RecoveryDisposition.NO_INTENT
        snapshot = self.snapshot(intent_id)
        if snapshot.state in {IntentState.RESERVED, IntentState.PROVEN_NOT_SENT}:
            return RecoveryDisposition.PROVEN_NOT_SENT
        if snapshot.state in {IntentState.ACCEPTED, IntentState.WRONG}:
            return RecoveryDisposition.SETTLED
        return RecoveryDisposition.RECONCILE

    def duplicate_disposition(
        self, scope: EvidenceScope, candidate: bytes
    ) -> DuplicateDisposition:
        with closing(self._connect()) as connection:
            _, duplicate_key = self._duplicate_key(connection, scope, candidate)
            row = connection.execute(
                "SELECT state FROM submission_intents WHERE duplicate_key = ?",
                (duplicate_key,),
            ).fetchone()
        if row is None:
            return DuplicateDisposition.NEW
        return {
            IntentState.RESERVED: DuplicateDisposition.RESERVED,
            IntentState.PROVEN_NOT_SENT: DuplicateDisposition.RESERVED,
            IntentState.DISPATCH_POSSIBLE: DuplicateDisposition.DISPATCH_POSSIBLE,
            IntentState.UNKNOWN: DuplicateDisposition.UNKNOWN,
            IntentState.RECONCILE: DuplicateDisposition.UNKNOWN,
            IntentState.WRONG: DuplicateDisposition.WRONG,
            IntentState.ACCEPTED: DuplicateDisposition.ACCEPTED,
            IntentState.CONFLICT: DuplicateDisposition.CONFLICT,
        }[IntentState(row["state"])]

    def diagnostics(self) -> dict[str, int]:
        with closing(self._connect()) as connection:
            states = {
                row["state"]: row["count"]
                for row in connection.execute(
                    "SELECT state, COUNT(*) AS count FROM submission_intents GROUP BY state"
                )
            }
            live_successes = connection.execute(
                """
                SELECT COUNT(DISTINCT intent_id) AS count
                FROM submission_events
                WHERE outcome = ? AND authoritative = 1 AND attributable = 1
                  AND synthetic = 0
                """,
                (AdapterOutcome.ACCEPTED.value,),
            ).fetchone()["count"]
            event_count = connection.execute(
                "SELECT COUNT(*) AS count FROM submission_events"
            ).fetchone()["count"]
        return {
            "intents": sum(states.values()),
            "events": event_count,
            "duplicate_suppression_records": sum(states.values()),
            "unknown": states.get(IntentState.UNKNOWN.value, 0)
            + states.get(IntentState.RECONCILE.value, 0),
            "wrong": states.get(IntentState.WRONG.value, 0),
            "live_successes": live_successes,
        }

    def enforce_capacity(self, maximum_intents: int) -> None:
        """Refuse new work rather than evict required deduplication state."""
        if type(maximum_intents) is not int or maximum_intents <= 0:
            raise ValueError("maximum_intents must be positive")
        with closing(self._connect()) as connection:
            count = connection.execute(
                "SELECT COUNT(*) AS count FROM submission_intents"
            ).fetchone()["count"]
        if count >= maximum_intents:
            raise StoragePressure(
                "intent capacity reached; unresolved and settled duplicate records are preserved"
            )
