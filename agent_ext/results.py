"""Recoverable projection for an explicitly internal result fixture.

This is not the organiser's ``/work/results.json`` schema and it is not a second
submission path.  It exercises state/projection crash boundaries until Jerome
wires the owned semantics to the inherited authoritative writer.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import tempfile
import threading
import time
from collections.abc import Callable, Mapping
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_PRIVATE = re.compile(
    r"(?:INCYPHER\{|https?://|\bBearer\s+|CTF(?:D)?_TOKEN|LLM_API_KEY|api[_-]?key\s*[=:])",
    re.IGNORECASE,
)
_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


def _path_lock(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(key, threading.RLock())


def _sanitise(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        if _PRIVATE.search(value):
            raise ValueError("internal projection payload contains private material")
        return value
    if isinstance(value, (list, tuple)):
        return [_sanitise(item) for item in value]
    if isinstance(value, Mapping):
        return {str(key): _sanitise(item) for key, item in value.items()}
    raise ValueError("projection payload must be JSON compatible")


@dataclass(frozen=True)
class InternalResultEntry:
    entry_id: str
    challenge_id: int
    intent_id: str
    status: str
    synthetic: bool
    details: Mapping[str, Any]

    def __post_init__(self) -> None:
        for name in ("entry_id", "intent_id", "status"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or len(value) > 256:
                raise ValueError(f"{name} must be bounded and nonempty")
        if type(self.challenge_id) is not int or self.challenge_id <= 0:
            raise ValueError("challenge_id must be positive")
        if type(self.synthetic) is not bool:
            raise ValueError("synthetic must be boolean")
        _sanitise(self.details)


@dataclass(frozen=True)
class PublicationStatus:
    state_revision: int
    published_revision: int
    current: bool


class InternalResultProjector:
    """Project committed internal rows via atomic same-directory replacement."""

    def __init__(
        self,
        database_path: str | os.PathLike[str],
        output_path: str | os.PathLike[str],
        *,
        before_replace: Callable[[Path, Path], None] | None = None,
        after_replace: Callable[[Path], None] | None = None,
    ):
        self.database_path = Path(database_path)
        self.output_path = Path(output_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.before_replace = before_replace
        self.after_replace = after_replace
        self._lock = _path_lock(self.output_path)
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path, timeout=30, isolation_level=None
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def _initialise(self) -> None:
        with closing(self._connect()) as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS internal_result_entries (
                    entry_id TEXT PRIMARY KEY,
                    challenge_id INTEGER NOT NULL,
                    intent_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    synthetic INTEGER NOT NULL,
                    details_json TEXT NOT NULL,
                    committed_revision INTEGER NOT NULL,
                    committed_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS internal_publication (
                    singleton INTEGER PRIMARY KEY CHECK(singleton = 1),
                    state_revision INTEGER NOT NULL,
                    published_revision INTEGER NOT NULL
                );
                INSERT OR IGNORE INTO internal_publication(
                    singleton, state_revision, published_revision
                ) VALUES(1, 0, 0);
                """
            )

    def commit_entry(self, entry: InternalResultEntry) -> int:
        if not isinstance(entry, InternalResultEntry):
            raise ValueError("InternalResultEntry required")
        details = json.dumps(
            _sanitise(entry.details),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            prior = connection.execute(
                "SELECT * FROM internal_result_entries WHERE entry_id = ?",
                (entry.entry_id,),
            ).fetchone()
            if prior is not None:
                same = (
                    prior["challenge_id"] == entry.challenge_id
                    and prior["intent_id"] == entry.intent_id
                    and prior["status"] == entry.status
                    and bool(prior["synthetic"]) == entry.synthetic
                    and prior["details_json"] == details
                )
                connection.execute("COMMIT")
                if not same:
                    raise ValueError("entry identity replayed with contradictory content")
                return prior["committed_revision"]
            row = connection.execute(
                "SELECT state_revision FROM internal_publication WHERE singleton = 1"
            ).fetchone()
            revision = row["state_revision"] + 1
            connection.execute(
                """
                INSERT INTO internal_result_entries(
                    entry_id, challenge_id, intent_id, status, synthetic,
                    details_json, committed_revision, committed_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.entry_id,
                    entry.challenge_id,
                    entry.intent_id,
                    entry.status,
                    int(entry.synthetic),
                    details,
                    revision,
                    time.time(),
                ),
            )
            connection.execute(
                "UPDATE internal_publication SET state_revision = ? WHERE singleton = 1",
                (revision,),
            )
            connection.execute("COMMIT")
            return revision

    def _snapshot(self) -> tuple[int, list[dict[str, Any]]]:
        with closing(self._connect()) as connection:
            connection.execute("BEGIN")
            revision = connection.execute(
                "SELECT state_revision FROM internal_publication WHERE singleton = 1"
            ).fetchone()["state_revision"]
            rows = connection.execute(
                """
                SELECT entry_id, challenge_id, intent_id, status, synthetic,
                       details_json, committed_revision
                FROM internal_result_entries
                WHERE committed_revision <= ?
                ORDER BY committed_revision, entry_id
                """,
                (revision,),
            ).fetchall()
            connection.execute("COMMIT")
        entries = [
            {
                "entry_id": row["entry_id"],
                "challenge_id": row["challenge_id"],
                "intent_id": row["intent_id"],
                "status": row["status"],
                "synthetic": bool(row["synthetic"]),
                "details": json.loads(row["details_json"]),
            }
            for row in rows
        ]
        return revision, entries

    def project(self) -> PublicationStatus:
        with self._lock:
            revision, entries = self._snapshot()
            packet = {
                "schema": "internal-result-fixture-v1",
                "revision": revision,
                "live_successes": sum(
                    1
                    for item in entries
                    if item["status"] == "accepted" and not item["synthetic"]
                ),
                "entries": entries,
            }
            temporary_path: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    "w",
                    encoding="utf-8",
                    delete=False,
                    dir=self.output_path.parent,
                    prefix=self.output_path.name + ".",
                    suffix=".tmp",
                ) as stream:
                    temporary_path = Path(stream.name)
                    json.dump(
                        packet,
                        stream,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    stream.flush()
                    os.fsync(stream.fileno())
                if self.before_replace is not None:
                    self.before_replace(self.output_path, temporary_path)
                os.replace(temporary_path, self.output_path)
                temporary_path = None
                self._sync_directory()
                if self.after_replace is not None:
                    self.after_replace(self.output_path)
                self._mark_published(revision)
            finally:
                if temporary_path is not None:
                    try:
                        temporary_path.unlink()
                    except FileNotFoundError:
                        pass
            return self.publication_status()

    def _sync_directory(self) -> None:
        flags = getattr(os, "O_RDONLY", 0) | getattr(os, "O_DIRECTORY", 0)
        try:
            descriptor = os.open(self.output_path.parent, flags)
        except (OSError, TypeError):
            return
        try:
            os.fsync(descriptor)
        except OSError:
            pass
        finally:
            os.close(descriptor)

    def _mark_published(self, revision: int) -> None:
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = connection.execute(
                "SELECT published_revision FROM internal_publication WHERE singleton = 1"
            ).fetchone()["published_revision"]
            connection.execute(
                "UPDATE internal_publication SET published_revision = ? WHERE singleton = 1",
                (max(current, revision),),
            )
            connection.execute("COMMIT")

    def publication_status(self) -> PublicationStatus:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT state_revision, published_revision
                FROM internal_publication WHERE singleton = 1
                """
            ).fetchone()
        return PublicationStatus(
            row["state_revision"],
            row["published_revision"],
            row["state_revision"] == row["published_revision"],
        )

    def reconcile(self) -> PublicationStatus:
        """Rebuild stale/missing output, or repair bookkeeping after replacement."""
        with self._lock:
            state = self.publication_status()
            try:
                packet = json.loads(self.output_path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError):
                packet = None
            if (
                isinstance(packet, dict)
                and packet.get("schema") == "internal-result-fixture-v1"
                and packet.get("revision") == state.state_revision
            ):
                self._mark_published(state.state_revision)
                return self.publication_status()
            return self.project()

    def commit_and_project(self, entry: InternalResultEntry) -> PublicationStatus:
        with self._lock:
            self.commit_entry(entry)
            return self.project()
