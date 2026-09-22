"""Bounded synchronous/asynchronous shell supervision for one trusted attempt."""

from __future__ import annotations

import os
import re
import selectors
import signal
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass

from .resources import Admission, AdmissionError, Capacity, Cost


_OUTPUT_BYTES = 12_000
_MAX_HANDLES = 2
_HEAVY_MARKERS = (
    "gdb", "binwalk", "nmap", "objdump", "radare", "python", "find ",
    "tesseract", "pdftotext", "pdftoppm", "pdfimages", "7z ",
)
RESOURCE_STATUSES = frozenset({
    "output_limit", "cost_exceeds_capacity", "queue_timeout", "queue_full",
    "confinement_unavailable", "execution_error", "cleanup_failed",
})
_QUIET_FAILURE_STATUSES = RESOURCE_STATUSES | {"timeout", "cancelled"}
_PROJECTION_HEADER = re.compile(r"^\[shell status=([a-z_]+)[^]]*](?:\n(.*))?$", re.S)


def parse_shell_projection(output: str) -> tuple[str | None, bool]:
    """Return a managed status and whether the projection contains payload evidence."""
    if not isinstance(output, str):
        return None, False
    match = _PROJECTION_HEADER.fullmatch(output.strip())
    if match is None:
        return None, bool(output.strip())
    return match.group(1), bool((match.group(2) or "").strip())


def quiet_shell_failure(output: str) -> bool:
    status, has_payload = parse_shell_projection(output)
    return status in _QUIET_FAILURE_STATUSES and not has_payload


def _environment() -> dict[str, str]:
    return {
        "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "TMPDIR": "/tmp",
        "PYTHONPATH": "/opt/agent",
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def _heavy(command: str) -> bool:
    lowered = command.lower()
    return any(marker in lowered for marker in _HEAVY_MARKERS)


@dataclass(frozen=True)
class ShellResult:
    status: str
    output: str
    exit_code: int | None
    elapsed_seconds: float
    truncated: bool = False

    def project(self) -> str:
        header = (
            f"[shell status={self.status} exit={self.exit_code} "
            f"elapsed={self.elapsed_seconds:.3f}s truncated={str(self.truncated).lower()}]"
        )
        return header + ("\n" + self.output if self.output else "")


class _Job:
    def __init__(self, handle: str, command: str, deadline: float, cost: Cost):
        self.handle = handle
        self.command = command
        self.deadline = deadline
        self.cost = cost
        self.cancelled = threading.Event()
        self.done = threading.Event()
        self.process: subprocess.Popen | None = None
        self.result: ShellResult | None = None
        self.reaped = False


class ManagedShell:
    """Callable drop-in for inherited ``run_bash`` plus bounded handle methods."""

    def __init__(
        self,
        scope_ref: str,
        deadline_monotonic: float,
        *,
        admission: Admission | None = None,
        ordinary_seconds: float = 45.0,
        heavy_seconds: float = 90.0,
        output_bytes: int = _OUTPUT_BYTES,
        cwd: str | None = None,
    ):
        if not isinstance(scope_ref, str) or not scope_ref or len(scope_ref) > 256:
            raise ValueError("scope_ref must be bounded")
        if not isinstance(deadline_monotonic, (int, float)):
            raise ValueError("deadline must be numeric")
        for value in (ordinary_seconds, heavy_seconds):
            if not isinstance(value, (int, float)) or not 0 < value <= 90:
                raise ValueError("shell timeout must be in (0, 90]")
        if type(output_bytes) is not int or not 1024 <= output_bytes <= 64 * 1024:
            raise ValueError("output bound is unsupported")
        self.scope_ref = scope_ref
        self.deadline = float(deadline_monotonic)
        self.admission = admission or Admission(
            Capacity(512 * 1024 * 1024, 64, active=2, heavy=1, queued=8)
        )
        self.ordinary_seconds = float(ordinary_seconds)
        self.heavy_seconds = float(heavy_seconds)
        self.output_bytes = output_bytes
        selected_cwd = cwd or os.getcwd()
        trusted_cwd = isinstance(selected_cwd, str) and (
            selected_cwd in {"/opt/agent", "/work", "/tmp"}
            or selected_cwd.startswith(("/opt/agent/", "/work/", "/tmp/"))
        )
        if (
            not isinstance(selected_cwd, str)
            or not os.path.isabs(selected_cwd)
            or not os.path.isdir(selected_cwd)
            or not trusted_cwd
        ):
            raise ValueError("shell cwd must be a trusted runtime directory")
        self.cwd = selected_cwd
        self._jobs: dict[str, _Job] = {}
        self._lock = threading.RLock()
        self._closed = False

    @property
    def supports_async(self) -> bool:
        return True

    def _new_job(self, command: str) -> _Job:
        if not isinstance(command, str) or not command.strip() or len(command) > 16_384:
            raise ValueError("command must be a bounded nonempty string")
        with self._lock:
            if self._closed:
                raise RuntimeError("shell supervisor is closed")
            if len(self._jobs) >= _MAX_HANDLES:
                raise RuntimeError("shell handle limit reached")
            is_heavy = _heavy(command)
            timeout = self.heavy_seconds if is_heavy else self.ordinary_seconds
            deadline = min(self.deadline, time.monotonic() + timeout)
            handle = "job-" + uuid.uuid4().hex[:12]
            cost = Cost(
                384 * 1024 * 1024 if is_heavy else 128 * 1024 * 1024,
                pids=48 if is_heavy else 8,
                heavy=is_heavy,
            )
            job = _Job(handle, command, deadline, cost)
            self._jobs[handle] = job
        thread = threading.Thread(
            target=self._execute, args=(job,), name="managed-shell-" + handle, daemon=True
        )
        thread.start()
        return job

    @staticmethod
    def _kill(process: subprocess.Popen | None) -> None:
        if process is None:
            return
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass

    def _execute(self, job: _Job) -> None:
        started = time.monotonic()
        output = bytearray()
        status = "error"
        code = None
        truncated = False
        process = None
        try:
            if not sys.platform.startswith("linux") or not (
                os.path.exists("/usr/bin/prlimit") and os.path.exists("/bin/bash")
            ):
                status = "confinement_unavailable"
                return
            if started >= job.deadline:
                status = "timeout"
                return
            with self.admission.acquire(
                job.cost, deadline=job.deadline, cancellation=job.cancelled
            ):
                argv = [
                    "/usr/bin/prlimit",
                    f"--as={job.cost.memory_bytes}",
                    "--nofile=128",
                    "--core=0",
                    "--",
                    "/bin/bash",
                    "-lc",
                    job.command,
                ]
                process = subprocess.Popen(
                    argv,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=self.cwd,
                    env=_environment(),
                    start_new_session=True,
                    close_fds=True,
                )
                job.process = process
                with selectors.DefaultSelector() as selector:
                    for stream in (process.stdout, process.stderr):
                        assert stream is not None
                        os.set_blocking(stream.fileno(), False)
                        selector.register(stream, selectors.EVENT_READ)
                    while selector.get_map() or process.poll() is None:
                        if job.cancelled.is_set():
                            status = "cancelled"
                            break
                        remaining = job.deadline - time.monotonic()
                        if remaining <= 0:
                            status = "timeout"
                            break
                        for key, _ in selector.select(min(remaining, 0.05)):
                            chunk = os.read(key.fileobj.fileno(), 4096)
                            if not chunk:
                                selector.unregister(key.fileobj)
                                continue
                            room = self.output_bytes - len(output)
                            output.extend(chunk[:room])
                            if len(chunk) > room or len(output) >= self.output_bytes:
                                truncated = True
                                status = "output_limit"
                                break
                        if status in {"cancelled", "timeout", "output_limit"}:
                            break
                if status in {"cancelled", "timeout", "output_limit"}:
                    self._kill(process)
                code = process.wait(timeout=2)
                if status == "error":
                    status = "ok" if code == 0 else "nonzero"
        except AdmissionError as exc:
            status = str(exc)
        except (OSError, subprocess.SubprocessError):
            status = "execution_error"
        finally:
            self._kill(process)
            if process is not None:
                try:
                    process.wait(timeout=1)
                    job.reaped = True
                except subprocess.SubprocessError:
                    self._kill(process)
                    try:
                        process.wait(timeout=1)
                        job.reaped = True
                    except subprocess.SubprocessError:
                        status = "cleanup_failed"
                for stream in (process.stdout, process.stderr):
                    if stream is not None:
                        stream.close()
            else:
                job.reaped = True
            text = bytes(output).decode("utf-8", errors="replace")
            if not text.strip() and status == "ok":
                text = "(no output)"
            job.result = ShellResult(
                status, text, code, max(0.0, time.monotonic() - started), truncated
            )
            job.done.set()

    def start(self, command: str) -> str:
        try:
            return self._new_job(command).handle
        except (RuntimeError, ValueError) as exc:
            return "error:" + str(exc)

    def poll(self, handle: str, wait_seconds: float = 0.0) -> str:
        if not isinstance(wait_seconds, (int, float)) or not 0 <= wait_seconds <= 5:
            return "error:poll wait must be between 0 and 5 seconds"
        with self._lock:
            job = self._jobs.get(handle)
        if job is None:
            return "error:unknown shell handle"
        job.done.wait(float(wait_seconds))
        if not job.done.is_set():
            return "running:" + handle
        if not job.reaped:
            raise RuntimeError("shell job cleanup failed")
        with self._lock:
            self._jobs.pop(handle, None)
        assert job.result is not None
        return job.result.project()

    def cancel(self, handle: str) -> str:
        with self._lock:
            job = self._jobs.get(handle)
        if job is None:
            return "error:unknown shell handle"
        job.cancelled.set()
        self._kill(job.process)
        job.done.wait(2)
        if not job.done.is_set():
            self._kill(job.process)
            job.done.wait(1)
        if not job.done.is_set():
            raise RuntimeError("shell job cleanup failed")
        return self.poll(handle)

    def __call__(self, command: str) -> str:
        handle = self.start(command)
        if handle.startswith("error:"):
            return handle
        with self._lock:
            job = self._jobs[handle]
        remaining = max(0.0, job.deadline - time.monotonic()) + 2
        job.done.wait(remaining)
        if not job.done.is_set():
            job.cancelled.set()
            self._kill(job.process)
            job.done.wait(2)
        if not job.done.is_set():
            raise RuntimeError("shell job cleanup failed")
        return self.poll(handle)

    def close(self) -> None:
        with self._lock:
            self._closed = True
            jobs = list(self._jobs.values())
        for job in jobs:
            job.cancelled.set()
            self._kill(job.process)
        unfinished = []
        for job in jobs:
            job.done.wait(2)
            if not job.done.is_set() or not job.reaped:
                self._kill(job.process)
                if job.process is not None:
                    try:
                        job.process.wait(timeout=1)
                        job.reaped = True
                    except subprocess.SubprocessError:
                        pass
                job.done.wait(1)
            if not job.done.is_set() or not job.reaped:
                unfinished.append(job)
        with self._lock:
            self._jobs = {job.handle: job for job in unfinished}
        if unfinished:
            raise RuntimeError("shell job cleanup failed")

    def snapshot(self) -> dict[str, int | bool]:
        with self._lock:
            return {"closed": self._closed, "handles": len(self._jobs), **self.admission.snapshot()}
