"""Private, bounded shell captures for same-scope continuation.

This database lives in writable /work, never in the image or official results.
Its contents may contain challenge secrets. Do not copy it to Git or diagnostics.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sqlite3
import uuid


MAX_OUTPUT_BYTES = 64 * 1024
MAX_COMMAND_BYTES = 16 * 1024
_HANDLE = re.compile(r"^capture-[0-9a-f]{24}$")


class OutputVault:
    def __init__(self, path: str | os.PathLike[str] = "/work/command-output.sqlite3"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)
        os.chmod(self.path, 0o600)
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS captures (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT,
                    scope_key TEXT NOT NULL,
                    handle TEXT NOT NULL UNIQUE,
                    command TEXT NOT NULL,
                    output TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS captures_scope ON captures(scope_key, seq);
            """)

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=1)
        db.execute("PRAGMA synchronous = FULL")
        return db

    def save(self, scope_key: str, command: str, output: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{64}", scope_key):
            raise ValueError("trusted scope key required")
        if not isinstance(command, str) or not isinstance(output, str):
            raise ValueError("shell capture must be text")
        if len(command.encode()) > MAX_COMMAND_BYTES:
            raise ValueError("shell command exceeds bound")
        raw = output.encode()
        if len(raw) > MAX_OUTPUT_BYTES:
            marker = "\n[private capture truncated at 64 KiB; rerun only if necessary]"
            raw = raw[:MAX_OUTPUT_BYTES - len(marker.encode())]
            output = raw.decode(errors="replace") + marker
        handle = "capture-" + uuid.uuid4().hex[:24]
        with self._connect() as db:
            db.execute("INSERT INTO captures(scope_key, handle, command, output) "
                       "VALUES(?, ?, ?, ?)", (scope_key, handle, command, output))
            db.execute("DELETE FROM captures WHERE scope_key = ? AND seq NOT IN "
                       "(SELECT seq FROM captures WHERE scope_key = ? "
                       "ORDER BY seq DESC LIMIT 16)", (scope_key, scope_key))
            db.execute("DELETE FROM captures WHERE seq NOT IN "
                       "(SELECT seq FROM captures ORDER BY seq DESC LIMIT 256)")
        return handle

    def read(self, scope_key: str, handle: str) -> str | None:
        if not re.fullmatch(r"[0-9a-f]{64}", scope_key) or not isinstance(handle, str):
            return None
        if not _HANDLE.fullmatch(handle):
            return None
        with self._connect() as db:
            row = db.execute("SELECT output FROM captures WHERE scope_key = ? "
                             "AND handle = ?", (scope_key, handle)).fetchone()
        return row[0] if row else None

    def project(self, scope_key: str) -> str:
        if not re.fullmatch(r"[0-9a-f]{64}", scope_key):
            raise ValueError("trusted scope key required")
        with self._connect() as db:
            rows = db.execute("SELECT handle, command, output FROM captures "
                              "WHERE scope_key = ? ORDER BY seq DESC LIMIT 4",
                              (scope_key,)).fetchall()
        return "\n".join(json.dumps({
            "handle": handle,
            "command": command[:160],
            "output_preview": output[:600],
            "full_output": "read_saved_output(handle) within this exact scope",
        }, ensure_ascii=False) for handle, command, output in rows)
