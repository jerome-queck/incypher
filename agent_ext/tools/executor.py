"""Fixed local inspection dispatcher using the merged team ToolResult contract.

This does not wrap the inherited run_bash callback: its capture and cancellation
properties cannot be strengthened after that callback has already returned.
"""
from __future__ import annotations

import json
import math
import os
import re
import selectors
import signal
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Callable

from agent_ext.contracts import Budget, ChallengeScope, FailureCategory, NextAction, ToolResult
from agent_ext.resources import Admission, AdmissionError, Cost
from .inspection import Limits, OPERATIONS, encode, observation_key

EvidenceSink = Callable[[ChallengeScope, str, dict], str]
_OPAQUE = re.compile(r"[A-Za-z0-9_.:-]{1,160}\Z")
_ERRORS = {
    "cancelled": FailureCategory.CANCELLED,
    "timeout": FailureCategory.TIMEOUT,
    "queue_timeout": FailureCategory.TIMEOUT,
    "malformed_worker_output": FailureCategory.MALFORMED_RESPONSE,
    "malformed_input": FailureCategory.MALFORMED_RESPONSE,
    "malformed_material": FailureCategory.MALFORMED_RESPONSE,
    "malformed_archive": FailureCategory.MALFORMED_RESPONSE,
    "source_changed": FailureCategory.TOOL_FAILURE,
    "unsupported_operation": FailureCategory.CONFIGURATION,
    "confinement_unavailable": FailureCategory.CONFIGURATION,
    "evidence_unavailable": FailureCategory.CONFIGURATION,
    "worker_unavailable": FailureCategory.CONFIGURATION,
}


def category(reason):
    if reason.endswith("_limit") or reason in {"queue_full", "cost_exceeds_capacity"}:
        return FailureCategory.RESOURCE_LIMIT
    return _ERRORS.get(reason, FailureCategory.TOOL_FAILURE)


def clean_environment(scratch: str):
    # No inherited environment, user PATH, Python startup hooks, HOME or secrets.
    return {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
            "TMPDIR": scratch, "PYTHONDONTWRITEBYTECODE": "1"}


def _run_worker(argv, request: bytes, scratch: str, *, deadline: float,
                cancellation: threading.Event | None, output_bytes: int):
    """Private trusted-argv primitive. Only the fixed worker is dispatched publicly.

    Worker code never forks or launches subprocesses. A private process group is
    killed defensively on every exit; wait() reaps our direct worker. This is NOT
    a general shell sandbox or a promise to reap arbitrary double-forked children.
    """
    output = bytearray()
    truncated = False
    reason = None
    if cancellation is not None and cancellation.is_set():
        return b"", None, "cancelled", False
    if time.monotonic() >= deadline:
        return b"", None, "timeout", False
    with subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, cwd=scratch, env=clean_environment(scratch),
                          start_new_session=True, close_fds=True) as process:
        try:
            process.stdin.write(request)
            process.stdin.close()
            with selectors.DefaultSelector() as selector:
                for stream in (process.stdout, process.stderr):
                    os.set_blocking(stream.fileno(), False)
                    selector.register(stream, selectors.EVENT_READ)
                while selector.get_map() or process.poll() is None:
                    if cancellation is not None and cancellation.is_set():
                        reason = "cancelled"
                        break
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        reason = "timeout"
                        break
                    for key, _ in selector.select(min(remaining, 0.02)):
                        chunk = os.read(key.fileobj.fileno(), 4096)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            continue
                        room = output_bytes - len(output)
                        output.extend(chunk[:room])
                        if len(chunk) > room:
                            truncated, reason = True, "output_limit"
                            break
                    if reason:
                        break
        finally:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
    return bytes(output), process.returncode, reason, truncated


class ToolExecutor:
    """One trusted scope/root per executor, one shared Admission across executors.

    Constructor values and EvidenceSink come from trusted integration code, never
    model arguments. The sink must return a private opaque reference and must
    itself be bounded by Richard's retention/cancellation contract.
    """

    def __init__(self, scope: ChallengeScope, material_root: str, admission: Admission,
                 evidence_sink: EvidenceSink, *, limits: Limits | None = None,
                 scratch_root: str = "/tmp", worker_memory_bytes: int = 128 * 1024 * 1024):
        self.scope, self.root, self.admission, self.sink = scope, material_root, admission, evidence_sink
        self.limits = limits or Limits()
        self.scratch_root = scratch_root
        self.cost = Cost(worker_memory_bytes, pids=1)
        if not callable(evidence_sink):
            raise ValueError("a private evidence sink is required")
        if worker_memory_bytes < 32 * 1024 * 1024:
            raise ValueError("worker address-space limit is too small")
        if len(encode([scope.challenge_id, scope.material_ref, scope.instance_generation])) > 2048:
            raise ValueError("scope identity is too large")

    def execute_action(self, action_id: str, action: NextAction, budget: Budget, *,
                       cancellation: threading.Event | None = None) -> ToolResult:
        """Project shared records into fixed operations; caller owns tool-call counts.

        Budget.steps_remaining is a model/decision allowance, not local concurrency.
        No shell string is parsed, translated, or silently routed to another backend.
        """
        if not isinstance(action, NextAction) or not isinstance(budget, Budget):
            raise ValueError("shared NextAction and Budget records are required")
        args = action.arguments
        valid = (isinstance(args, Mapping) and "path" in args
                 and not set(args).difference({"path", "offset"}))
        return self.execute(action_id, action.kind, args["path"] if valid else None,
                            offset=args.get("offset", 0) if valid else 0,
                            deadline_monotonic=budget.deadline_monotonic,
                            cancellation=cancellation)

    def execute(self, action_id: str, operation: str, path: str, *, offset: int = 0,
                timeout_seconds: float = 5.0, queue_seconds: float = 2.0,
                deadline_monotonic: float | None = None,
                cancellation: threading.Event | None = None) -> ToolResult:
        started = time.monotonic()
        if not isinstance(action_id, str) or not _OPAQUE.fullmatch(action_id):
            raise ValueError("action_id must be a bounded opaque identifier")
        for value in (timeout_seconds, queue_seconds):
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 120:
                raise ValueError("timeouts must be finite and in (0, 120]")
        if deadline_monotonic is not None and (
                type(deadline_monotonic) not in (int, float) or not math.isfinite(deadline_monotonic)):
            raise ValueError("caller deadline must be finite")
        overall_deadline = deadline_monotonic if deadline_monotonic is not None else started + queue_seconds + timeout_seconds
        queue_wait = 0.0

        def failure(reason, *, truncated=False, exit_code=None):
            excerpt = encode(dict(status="failed", reason=reason, truncated=truncated,
                                  queue_seconds=queue_wait)).decode("ascii")
            return ToolResult(action_id, "", (), excerpt, time.monotonic() - started,
                              exit_code=exit_code, error=category(reason))

        if not isinstance(operation, str) or operation not in OPERATIONS:
            return failure("unsupported_operation")
        if (not isinstance(path, str) or len(path) > 1024 or type(offset) is not int
                or not 0 <= offset <= self.limits.input_bytes):
            return failure("malformed_input")
        if not sys.platform.startswith("linux"):
            return failure("confinement_unavailable")
        if cancellation is not None and cancellation.is_set():
            return failure("cancelled")
        if time.monotonic() >= overall_deadline:
            return failure("timeout")
        # The source walker also checks every root component using O_NOFOLLOW.
        for root in (self.root, self.scratch_root):
            if (not isinstance(root, str) or len(root) > 1024
                    or not (root in {"/work", "/tmp"} or root.startswith(("/work/", "/tmp/")))
                    or any(p in {"", ".", ".."} for p in root.split("/")[1:])):
                return failure("unapproved_root")
        request = encode(dict(root=self.root, path=path, operation=operation, offset=offset,
                              limits=asdict(self.limits), memory_bytes=self.cost.memory_bytes))
        if len(request) > 4096:
            return failure("malformed_input")
        try:
            with self.admission.acquire(self.cost, deadline=min(started + queue_seconds, overall_deadline),
                                        cancellation=cancellation):
                queue_wait = time.monotonic() - started
                from .worker import open_root
                scratch_fd = open_root(self.scratch_root)
                os.close(scratch_fd)
                # Scratch root is trusted runtime configuration; integration must
                # prevent other actors renaming it while a call is active.
                with tempfile.TemporaryDirectory(prefix="aidan-tool-", dir=self.scratch_root) as scratch:
                    worker = str(Path(__file__).with_name("worker.py").resolve())
                    output, code, reason, truncated = _run_worker(
                        [sys.executable, "-I", "-B", worker], request, scratch,
                        deadline=min(time.monotonic() + timeout_seconds, overall_deadline),
                        cancellation=cancellation, output_bytes=self.limits.output_bytes + 1024)
                if reason:
                    return failure(reason, truncated=truncated, exit_code=code)
                if code:
                    return failure("worker_failed", exit_code=code)
                if cancellation is not None and cancellation.is_set():
                    return failure("cancelled", exit_code=code)
                if time.monotonic() >= overall_deadline:
                    return failure("timeout", exit_code=code)
                try:
                    payload = json.loads(output)
                    if not isinstance(payload, dict):
                        raise ValueError()
                    if "error" in payload:
                        reason = payload["error"]
                        if not isinstance(reason, str) or not re.fullmatch(r"[a-z_]{1,64}", reason):
                            raise ValueError()
                        return failure(reason, exit_code=code)
                    observation = payload["observation"]
                    digest = payload["sha256"]
                    peak = payload["worker_peak_rss_bytes"]
                    if (not isinstance(observation, dict) or not isinstance(digest, str)
                            or not re.fullmatch(r"[0-9a-f]{64}", digest)
                            or type(peak) is not int or peak < 0):
                        raise ValueError()
                    if (observation.get("operation") != operation
                            or type(observation.get("truncated")) is not bool
                            or type(observation.get("source_bytes")) is not int
                            or not 0 <= observation["source_bytes"] <= self.limits.input_bytes):
                        raise ValueError()
                    key = observation_key(self.scope, digest, operation, offset, self.limits)
                    observation.update(status="ok", material_sha256=digest,
                                       queue_seconds=queue_wait, worker_peak_rss_bytes=peak,
                                       container_peak_memory_bytes=None, container_peak_pids=None)
                    excerpt = encode(observation)
                    if len(excerpt) > self.limits.output_bytes:
                        return failure("observation_limit", truncated=True, exit_code=code)
                except (ValueError, KeyError, TypeError, OverflowError):
                    return failure("malformed_worker_output", exit_code=code)
                try:
                    evidence_ref = self.sink(self.scope, key, json.loads(excerpt))
                    if not isinstance(evidence_ref, str) or not _OPAQUE.fullmatch(evidence_ref):
                        raise ValueError()
                except Exception:
                    return failure("evidence_unavailable", exit_code=code)
                if cancellation is not None and cancellation.is_set():
                    return failure("cancelled", exit_code=code)
                if time.monotonic() >= overall_deadline:
                    return failure("timeout", exit_code=code)
                return ToolResult(action_id, evidence_ref, (key,), excerpt.decode("ascii"),
                                  time.monotonic() - started, exit_code=code)
        except AdmissionError as exc:
            queue_wait = time.monotonic() - started
            return failure(str(exc))
        except FileNotFoundError:
            return failure("worker_unavailable")
        except (OSError, ValueError):
            return failure("execution_unavailable")
