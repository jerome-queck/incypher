#!/usr/bin/env python3
"""Strict coordinator wrappers around the inspected organiser harness."""

from __future__ import annotations

import ast
import hashlib
import importlib
import inspect
import math
import os
import textwrap
import time
from collections.abc import Mapping

from agent_ext.managed_shell import ManagedShell, RESOURCE_STATUSES, parse_shell_projection
from agent_ext.resources import Admission, Capacity
from agent_ext.runtime_context import (
    Finding,
    FindingDisposition,
    bind_prepared_material,
    current_attempt,
    trusted_attempt,
)
from agent_ext.runtime_state import AttemptOutcome, RuntimeState, RuntimeStateError


_MAIN_MARKERS = (
    "client = CTFdClient(base, token)",
    "allch = client.list_challenges()",
    'targets = [c for c in targets if c["id"] in only]',
    'targets = [c for c in targets if (c.get("category") or "").lower() in cats]',
    'targets.sort(key=lambda c: c["id"])',
    "ch = client.challenge(cid)",
    "res = solve_challenge(client, ch, max_steps)",
    "results.append(res)",
    'open(f"{WORK}/results.json", "w")',
)
_OFFICIAL_AST = {
    "main": "d28a60bcc5f8168c42d0bec40728d161d648323418aadd965c2b9310c5cb460b",
    "solve": "a20e9ee542b68283728f9a8800d9384b2eb44da1a931a97b99551ee7fd562ac1",
    "prompt": "e94d78fc4a93901c67e8467c24d3c306873d077d478e125b35acd0b790d66ee6",
    "shell": "5e127a5d448b71c6f65ca6d938175a0bcc0c8bdf74313b3498cea6fb92d3ea0b",
    "catalogue": "40a1220cf274ee54b0c3aa77a7504fae77256d496c778fd43c646c3815f74ba2",
    "detail": "a04d71af3e0fa8eab901da59d5a009fc75937e899dd9ff749e2b7b539fa4f6fe",
    "is_practice": "d6e6b7c08dbe14b5094e557787c911c792e488ba163fbb11f10f36772371aa05",
    "client_init": "40b975045df8353cd811139e3fdd9266f976daa68c416e7a0db5a5aa92552b2c",
}
_MAX_SLICE_MODEL_CALLS = 150
_MAX_RUN_SECONDS = 24 * 60 * 60
_PASS_COOLDOWN_SECONDS = 2.0
_CATALOGUE_REFRESH_SECONDS = 300.0


def _require_signature(function, names, label):
    if not callable(function) or tuple(inspect.signature(function).parameters) != tuple(names):
        raise RuntimeError(f"Official {label} hook changed; inspect base contract")


def _require_ast(function, expected: str, label: str) -> None:
    try:
        source = textwrap.dedent(inspect.getsource(function))
        normalized = ast.dump(ast.parse(source), include_attributes=False)
        observed = hashlib.sha256(normalized.encode()).hexdigest()
    except (OSError, TypeError, SyntaxError):
        observed = ""
    if observed != expected:
        raise RuntimeError(f"Official {label} implementation changed; inspect base contract")


def _require_main_contract(module) -> None:
    inherited_main = getattr(module, "main", None)
    _require_signature(inherited_main, (), "main")
    if getattr(module, "__file__", None):
        _require_ast(inherited_main, _OFFICIAL_AST["main"], "main")
        source = inspect.getsource(inherited_main)
        if any(marker not in source for marker in _MAIN_MARKERS):
            raise RuntimeError("Official main control flow changed; inspect base contract")


class _RankedId(int):
    """An int-compatible catalogue ID whose ordering carries a trusted rank."""

    def __new__(cls, value: int, rank: int):
        item = int.__new__(cls, value)
        item.rank = rank
        return item

    def __lt__(self, other):
        if isinstance(other, _RankedId):
            return self.rank < other.rank
        return int.__lt__(self, other)


class _CatalogueCache:
    """Bound trusted catalogue reads while allowing local reranking every slice."""

    def __init__(self, clock=None):
        self._clock = clock or time.monotonic
        self._briefs: tuple[dict, ...] | None = None
        self._refresh_at = 0.0

    def list_challenges(self, delegate) -> list[dict]:
        now = float(self._clock())
        if not math.isfinite(now):
            raise RuntimeError("Catalogue clock changed; inspect runtime")
        if self._briefs is None or now >= self._refresh_at:
            try:
                briefs = delegate.list_challenges()
            except (OSError, TimeoutError):
                if self._briefs is None:
                    raise
                self._refresh_at = now + _CATALOGUE_REFRESH_SECONDS
                return [dict(item) for item in self._briefs]
            if not isinstance(briefs, list) or any(
                not isinstance(item, Mapping) for item in briefs
            ):
                raise RuntimeError("Official challenge catalogue changed; inspect base contract")
            self._briefs = tuple(dict(item) for item in briefs)
            self._refresh_at = now + _CATALOGUE_REFRESH_SECONDS
        return [dict(item) for item in self._briefs]

    def mark_solved(self, challenge_id: int) -> None:
        if type(challenge_id) is not int or challenge_id <= 0 or self._briefs is None:
            return
        updated = []
        for brief in self._briefs:
            copied = dict(brief)
            if copied.get("id") == challenge_id:
                copied["solved"] = True
            updated.append(copied)
        self._briefs = tuple(updated)


class _RankedClient:
    def __init__(
        self,
        delegate,
        state: RuntimeState,
        catalogue: _CatalogueCache | None = None,
    ):
        self._delegate = delegate
        self._state = state
        self._catalogue = catalogue or _CatalogueCache()
        self._solved: set[int] = set()

    def list_challenges(self):
        briefs = self._catalogue.list_challenges(self._delegate)
        ordered = self._state.rank_briefs(briefs)
        ranked = []
        self._solved = set()
        for rank, brief in enumerate(ordered):
            cid = brief.get("id")
            if type(cid) is not int or cid <= 0 or type(brief.get("solved", False)) is not bool:
                raise RuntimeError("Official challenge brief changed; inspect base contract")
            if brief.get("solved") is True:
                self._solved.add(cid)
            copied = dict(brief)
            copied["id"] = _RankedId(cid, rank)
            ranked.append(copied)
        return ranked

    def challenge(self, challenge_id):
        if not isinstance(challenge_id, int):
            raise RuntimeError("Official challenge ID changed; inspect base contract")
        return self._delegate.challenge(int(challenge_id))

    def trusted_solved(self, challenge_id: int) -> bool:
        return int(challenge_id) in self._solved

    def mark_solved(self, challenge_id: int) -> None:
        self._catalogue.mark_solved(challenge_id)

    def __getattr__(self, name):
        return getattr(self._delegate, name)


def _shell_summary(output: str) -> str:
    status, _ = parse_shell_projection(output)
    return "bounded shell outcome: " + (status or "rejected")


class _StatefulShell:
    """Lazy per-attempt shell that adds scoped dedupe and durable summaries."""

    supports_async = True

    def __init__(self, state: RuntimeState, admission: Admission, cwd: str):
        self._state = state
        self._admission = admission
        self._cwd = cwd
        self._shell: ManagedShell | None = None
        self._context = None
        self._commands: dict[str, str] = {}
        self._failure: AttemptOutcome | None = None
        self._progress = 0
        self._model_progress = 0

    def _get_shell(self) -> ManagedShell:
        if self._shell is None:
            context = current_attempt(required=True)
            self._context = context
            self._shell = ManagedShell(
                context.material_ref,
                context.deadline_monotonic,
                admission=self._admission,
                cwd=self._cwd,
            )
        return self._shell

    def _duplicate(self, command: str) -> bool:
        context = current_attempt(required=True)
        return command in self._commands.values() or self._state.lookup(context, command)

    def _record(self, command: str, output: str) -> None:
        status, has_payload = parse_shell_projection(output)
        classified = None
        if status == "timeout":
            classified = AttemptOutcome.TIMEOUT
        elif status == "cancelled":
            classified = AttemptOutcome.CANCELLED
        elif status in RESOURCE_STATUSES:
            classified = AttemptOutcome.RESOURCE
        priority = {
            None: 0,
            AttemptOutcome.CANCELLED: 1,
            AttemptOutcome.TIMEOUT: 2,
            AttemptOutcome.RESOURCE: 3,
        }
        if priority[classified] > priority[self._failure]:
            self._failure = classified
        context = self._context or current_attempt(required=True)
        recorded = self._state.record(
            context,
            command,
            output,
            _shell_summary(output),
            progress=1,
        )
        if recorded:
            self._state.record_challenge_progress(context.challenge_id)
            self._progress += 1

    def record_model_progress(self) -> None:
        context = current_attempt(required=True)
        self._state.record_challenge_progress(context.challenge_id)
        self._progress += 1
        self._model_progress += 1

    def checkpoint_finding(self, finding: Finding) -> FindingDisposition:
        context = current_attempt(required=True)
        disposition = self._state.checkpoint_finding(context, finding)
        if disposition is FindingDisposition.SAVED:
            self._state.record_challenge_progress(context.challenge_id)
            self._progress += 1
        return disposition

    def __call__(self, command: str) -> str:
        if self._duplicate(command):
            return "duplicate:no new evidence; choose a materially different command"
        output = self._get_shell()(command)
        self._record(command, output)
        return output

    def start(self, command: str) -> str:
        if self._duplicate(command):
            return "duplicate:no new evidence; choose a materially different command"
        handle = self._get_shell().start(command)
        if handle.startswith("job-"):
            self._commands[handle] = command
        elif handle.startswith("error:"):
            self._failure = AttemptOutcome.RESOURCE
        return handle

    def poll(self, handle: str, wait_seconds: float = 0.0) -> str:
        output = self._get_shell().poll(handle, wait_seconds)
        if not output.startswith("running:") and handle in self._commands:
            command = self._commands.pop(handle)
            self._record(command, output)
        return output

    def cancel(self, handle: str) -> str:
        output = self._get_shell().cancel(handle)
        if handle in self._commands:
            command = self._commands.pop(handle)
            self._record(command, output)
        return output

    def close(self) -> None:
        if self._shell is not None:
            try:
                for handle in list(self._commands):
                    self.cancel(handle)
            finally:
                self._shell.close()
        self._commands.clear()

    def snapshot(self):
        if self._shell is None:
            return {"closed": False, "handles": 0, **self._admission.snapshot()}
        return self._shell.snapshot()

    @property
    def failure_outcome(self) -> AttemptOutcome | None:
        return self._failure

    @property
    def progress(self) -> int:
        return self._progress

    @property
    def model_progress(self) -> int:
        return self._model_progress

def _failure_class(result: Mapping, shell: _StatefulShell) -> AttemptOutcome:
    error = str(result.get("error", "")).lower()
    if error in {"tool call budget exhausted", "submission budget exhausted"}:
        return shell.failure_outcome or AttemptOutcome.UNSOLVED
    if "timeout" in error:
        return AttemptOutcome.TIMEOUT
    if any(word in error for word in ("resource", "capacity", "output_limit", "queue_")):
        return AttemptOutcome.RESOURCE
    if any(
        word in error
        for word in ("model request", "malformed model", "provider", "gateway", "budget")
    ):
        return AttemptOutcome.PROVIDER
    if "submission" in error or "verdict" in result:
        return AttemptOutcome.SUBMISSION
    if "cancel" in error:
        return AttemptOutcome.CANCELLED
    return shell.failure_outcome or AttemptOutcome.UNSOLVED


def _solved_result(challenge: Mapping) -> dict:
    return {
        "id": int(challenge["id"]),
        "name": challenge["name"],
        "category": challenge.get("category"),
        "type": challenge.get("type"),
        "had_files": False,
        "had_instance": False,
        "seconds": 0.0,
        "solved": True,
        "steps": 0,
        "model_calls": 0,
        "tool_calls": 0,
    }


def _deferred_result(challenge: Mapping, reason: str) -> dict:
    return {
        "id": int(challenge["id"]),
        "name": challenge.get("name", "unknown"),
        "category": challenge.get("category"),
        "type": challenge.get("type"),
        "had_files": False,
        "had_instance": False,
        "seconds": 0.0,
        "solved": False,
        "steps": 0,
        "model_calls": 0,
        "tool_calls": 0,
        "error": "coordinator stopped: " + reason,
    }


class _OuterCoordinator:
    """Bound repeated inherited lifecycles without owning their results."""

    def __init__(self):
        self.deadline = time.monotonic() + _MAX_RUN_SECONDS
        self.stop_reason: str | None = None
        self.begin_pass()

    def begin_pass(self) -> None:
        self.pass_calls = 0
        self.pass_slices = 0
        self.pass_all_solved = True

    def note_catalogue_solved(self) -> None:
        self.pass_calls += 1

    def admit(self, max_steps: int) -> tuple[int | None, str | None]:
        self.pass_calls += 1
        if self.stop_reason is not None:
            self.pass_all_solved = False
            return None, self.stop_reason
        if time.monotonic() >= self.deadline:
            self.stop_reason = "run deadline"
        if self.stop_reason is not None:
            self.pass_all_solved = False
            return None, self.stop_reason
        if self.pass_slices:
            self.pass_all_solved = False
            return None, "queue reschedule"
        self.pass_slices += 1
        return max_steps, None

    def note_result(
        self,
        *,
        solved: bool,
        budget_exhausted: bool = False,
    ) -> None:
        if time.monotonic() >= self.deadline:
            self.stop_reason = "run deadline"
        if budget_exhausted:
            self.stop_reason = "model budget exhausted"
        if not solved:
            self.pass_all_solved = False

    def should_continue(self) -> bool:
        if self.stop_reason is not None:
            return False
        if self.pass_calls == 0 or self.pass_slices == 0 or self.pass_all_solved:
            return False
        return time.monotonic() + _PASS_COOLDOWN_SECONDS < self.deadline


def main():
    import main as official_main

    _require_main_contract(official_main)
    inherited_is_practice = getattr(official_main, "is_practice", None)
    _require_signature(inherited_is_practice, ("ch",), "practice-selection")
    inherited_solve = getattr(official_main, "solve_challenge", None)
    _require_signature(inherited_solve, ("client", "ch", "max_steps"), "solve-challenge")
    inherited_client = getattr(official_main, "CTFdClient", None)
    _require_signature(inherited_client, ("base", "token"), "client-constructor")
    inherited_client_init = getattr(inherited_client, "__init__", None)
    _require_signature(
        inherited_client_init, ("self", "base", "token"), "client-constructor-init"
    )
    _require_signature(
        getattr(inherited_client, "list_challenges", None),
        ("self",),
        "client-catalogue",
    )
    _require_signature(
        getattr(inherited_client, "challenge", None),
        ("self", "cid"),
        "client-detail",
    )
    solver_module = importlib.import_module(inherited_solve.__module__)
    inherited_build_prompt = getattr(solver_module, "build_prompt", None)
    _require_signature(
        inherited_build_prompt,
        ("ch", "cdir", "filenames", "conn"),
        "prompt-construction",
    )
    inherited_run_bash = getattr(solver_module, "run_bash", None)
    _require_signature(inherited_run_bash, ("cmd",), "shell")
    if getattr(official_main, "__file__", None):
        _require_ast(
            inherited_is_practice, _OFFICIAL_AST["is_practice"], "practice-selection"
        )
        _require_ast(
            inherited_client_init, _OFFICIAL_AST["client_init"], "client-constructor"
        )
        _require_ast(inherited_solve, _OFFICIAL_AST["solve"], "solve-challenge")
        _require_ast(inherited_build_prompt, _OFFICIAL_AST["prompt"], "prompt-construction")
        _require_ast(inherited_run_bash, _OFFICIAL_AST["shell"], "shell")
        _require_ast(
            inherited_client.list_challenges, _OFFICIAL_AST["catalogue"], "client-catalogue"
        )
        _require_ast(inherited_client.challenge, _OFFICIAL_AST["detail"], "client-detail")

    state = RuntimeState(os.environ.get("RUNTIME_STATE_PATH", "/work/runtime-state.sqlite3"))
    admission = Admission(Capacity(512 * 1024 * 1024, 64, active=2, heavy=1, queued=8))
    validation_selector = os.path.isfile("/opt/agent/.validation-id")
    coordinator = _OuterCoordinator()
    catalogue = _CatalogueCache()

    def client_factory(base, token):
        return _RankedClient(inherited_client(base, token), state, catalogue)

    def scoped_build_prompt(ch, cdir, filenames, conn):
        context = bind_prepared_material(ch, cdir, filenames, conn)
        prompt = inherited_build_prompt(ch, cdir, filenames, conn)
        memory = state.project_memory(context)
        if memory.record_count:
            prompt = "## Restart-safe prior evidence\n" + memory.text + "\n\n" + prompt
        return prompt

    def scoped_solve(client, ch, max_steps):
        cid = ch.get("id")
        if (
            type(cid) is not int
            or cid <= 0
            or type(max_steps) is not int
            or not 1 <= max_steps <= _MAX_SLICE_MODEL_CALLS
        ):
            raise RuntimeError("Official solve arguments changed; inspect base contract")
        if not validation_selector and isinstance(client, _RankedClient) and client.trusted_solved(cid):
            coordinator.note_catalogue_solved()
            result = _solved_result(ch)
            state.record_challenge_outcome(int(cid), True, 0, AttemptOutcome.UNSOLVED)
            return result
        allocated_steps, deferred = coordinator.admit(max_steps)
        if deferred is not None:
            return _deferred_result(ch, deferred)
        assert allocated_steps is not None
        shell = _StatefulShell(state, admission, os.getcwd())
        started = time.perf_counter()
        with trusted_attempt(ch, deadline_monotonic=coordinator.deadline):
            solver_module.run_bash = shell
            try:
                result = inherited_solve(client, ch, allocated_steps)
            except (
                RuntimeStateError, OSError, ValueError, KeyError, TypeError,
                RuntimeError, TimeoutError,
            ) as exc:
                observed_model_calls = min(allocated_steps, shell.model_progress)
                state.record_challenge_outcome(
                    int(cid), False, shell.progress, AttemptOutcome.CRASH
                )
                state.checkpoint()
                coordinator.note_result(
                    solved=False,
                )
                return {
                    "id": int(cid),
                    "name": ch.get("name", "unknown"),
                    "category": ch.get("category"),
                    "type": ch.get("type"),
                    "had_files": False,
                    "had_instance": False,
                    "seconds": round(time.perf_counter() - started, 1),
                    "solved": False,
                    "steps": 0,
                    "model_calls": observed_model_calls,
                    "tool_calls": 0,
                    "error": f"{type(exc).__name__}: attempt crashed",
                }
            finally:
                solver_module.run_bash = inherited_run_bash
                shell.close()
        if not isinstance(result, Mapping):
            state.record_challenge_outcome(int(cid), False, 0, AttemptOutcome.CRASH)
            raise RuntimeError("Official solve result changed; inspect base contract")
        solved = result.get("solved") is True
        result_model_calls = result.get("model_calls", 0)
        if (
            type(result_model_calls) is not int
            or not 0 <= result_model_calls <= allocated_steps
        ):
            state.record_challenge_outcome(int(cid), False, 0, AttemptOutcome.CRASH)
            raise RuntimeError("Official model-call result changed; inspect base contract")
        observed_model_calls = max(result_model_calls, shell.model_progress)
        if observed_model_calls > allocated_steps:
            state.record_challenge_outcome(int(cid), False, 0, AttemptOutcome.CRASH)
            raise RuntimeError("Official model-call bound changed; inspect base contract")
        progress = max(shell.progress, min(
            1_000_000,
            max(0, int(result.get("model_calls", 0)))
            + max(0, int(result.get("tool_calls", 0))),
        ))
        outcome = AttemptOutcome.SOLVED if solved else _failure_class(result, shell)
        state.record_challenge_outcome(
            int(cid), solved, progress,
            outcome,
        )
        if solved and isinstance(client, _RankedClient):
            client.mark_solved(int(cid))
        state.checkpoint()
        coordinator.note_result(
            solved=solved,
            budget_exhausted=(
                str(result.get("error", "")).lower() == "model budget exhausted"
            ),
        )
        return result

    official_main.is_practice = lambda challenge: False
    official_main.CTFdClient = client_factory
    official_main.solve_challenge = scoped_solve
    solver_module.build_prompt = scoped_build_prompt
    pacing_was_set = "MODEL_SPEND_PACING" in os.environ
    pacing_before = os.environ.get("MODEL_SPEND_PACING")
    try:
        if not validation_selector and not pacing_was_set:
            os.environ["MODEL_SPEND_PACING"] = "adaptive"
        while True:
            coordinator.begin_pass()
            return_code = official_main.main()
            if return_code not in (None, 0) or not coordinator.should_continue():
                return return_code
            time.sleep(_PASS_COOLDOWN_SECONDS)
    finally:
        official_main.is_practice = inherited_is_practice
        official_main.CTFdClient = inherited_client
        official_main.solve_challenge = inherited_solve
        solver_module.build_prompt = inherited_build_prompt
        solver_module.run_bash = inherited_run_bash
        if pacing_was_set:
            assert pacing_before is not None
            os.environ["MODEL_SPEND_PACING"] = pacing_before
        else:
            os.environ.pop("MODEL_SPEND_PACING", None)


if __name__ == "__main__":
    raise SystemExit(main())
