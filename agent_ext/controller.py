"""Serial decision owner for the inherited harness; no HTTP, model, or result I/O.

Records here are private decision state. strategy_bridge projects the merged
team contracts; only trusted owners supply qualified scope, evidence and outcomes.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from enum import Enum
from itertools import islice

from .retry_policy import Failure, Operation, RetryAction, RetryLimits, retry_decision
from .scheduler import (
    Challenge,
    SchedulingRecord,
    Scope,
    SelectionPolicy,
    bounded_ref,
    finite_number,
    positive_int,
    select_challenge,
)


class EvidenceKind(str, Enum):
    OBSERVATION = "observation"
    DISCRIMINATING_TEST = "discriminating_test"
    REDUCED_UNCERTAINTY = "reduced_uncertainty"


def _fingerprint(value: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
        raise ValueError(
            "evidence and candidate fingerprints must be canonical SHA-256 references"
        )


@dataclass(frozen=True)
class ProgressEvidence:
    """Richard confirms scope and stable content identity; model prose is not evidence."""

    scope: Scope
    fingerprint: str
    kind: EvidenceKind = EvidenceKind.OBSERVATION
    confirmed: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.scope, Scope) or not isinstance(self.kind, EvidenceKind):
            raise ValueError("invalid evidence scope or kind")
        _fingerprint(self.fingerprint)
        if type(self.confirmed) is not bool:
            raise ValueError("confirmed must be boolean")


@dataclass(frozen=True)
class ControllerLimits:
    # Conservative SYNTHETIC experiment defaults, not measured live-run policy.
    run_seconds: float = 300
    attempt_seconds: float = 30
    idle_grace_seconds: float = 30
    catalogue_poll_seconds: float = 5
    max_attempts_per_scope: int = 4
    max_continuations_per_approach: int = 1
    max_bypasses: int = 3
    max_total_attempts: int = 100
    max_scopes: int = 256
    model_requests_per_attempt: int = 2
    tool_calls_per_attempt: int = 4
    max_model_requests: int = 20
    max_tool_calls: int = 40
    selection: SelectionPolicy = SelectionPolicy.PROGRESS
    retry: RetryLimits = field(default_factory=RetryLimits)

    def __post_init__(self) -> None:
        for name in (
            "run_seconds",
            "attempt_seconds",
            "idle_grace_seconds",
            "catalogue_poll_seconds",
        ):
            finite_number(getattr(self, name), name, positive=True)
        for name in (
            "max_attempts_per_scope",
            "max_bypasses",
            "max_total_attempts",
            "max_scopes",
        ):
            positive_int(getattr(self, name), name)
        for name in (
            "max_continuations_per_approach",
            "model_requests_per_attempt",
            "tool_calls_per_attempt",
            "max_model_requests",
            "max_tool_calls",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        if not isinstance(self.selection, SelectionPolicy) or not isinstance(
            self.retry, RetryLimits
        ):
            raise ValueError("invalid policy configuration")


@dataclass(frozen=True)
class AttemptBudget:
    seconds: float
    model_requests: int
    tool_calls: int


@dataclass(frozen=True)
class Attempt:
    token: int
    scope: Scope
    authority_ref: str
    approach_ref: str
    deadline: float
    budget: AttemptBudget
    repair: bool = False


class DecisionKind(str, Enum):
    ATTEMPT = "attempt"
    WAIT = "wait"
    STOP = "stop"


@dataclass(frozen=True)
class Decision:
    kind: DecisionKind
    reason: str
    attempt: Attempt | None = None
    wake_at: float | None = None
    refresh_catalogue: bool = False
    cancel_attempt_token: int | None = None
    checkpoint_required: bool = False
    release_resources: bool = False


@dataclass(frozen=True)
class AttemptReport:
    scope: Scope
    evidence: tuple[ProgressEvidence, ...] = ()
    candidate_ref: str | None = None
    failure: Failure | None = None
    model_requests: int = 0
    tool_calls: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.scope, Scope):
            raise ValueError("report requires a scope")
        if not isinstance(self.evidence, tuple) or len(self.evidence) > 32:
            raise ValueError("at most 32 immutable evidence references per report")
        if not all(isinstance(item, ProgressEvidence) for item in self.evidence):
            raise ValueError("invalid evidence record")
        if self.candidate_ref is not None:
            _fingerprint(self.candidate_ref)
        if self.failure is not None and not isinstance(self.failure, Failure):
            raise ValueError("invalid classified failure")
        if self.candidate_ref is not None and self.failure is not None:
            raise ValueError("candidate and failure are mutually exclusive")
        for value in (self.model_requests, self.tool_calls):
            if type(value) is not int or value < 0:
                raise ValueError("resource usage must be nonnegative integer counts")


class WorkState(str, Enum):
    READY = "ready"
    ACTIVE = "active"
    DEFERRED = "deferred"
    AWAITING_CANDIDATE = "awaiting_candidate"
    UNRESOLVED = "unresolved"
    TERMINAL = "terminal"
    SUPERSEDED = "superseded"


class Followup(str, Enum):
    NONE = "none"
    QUALIFY_CANDIDATE = "qualify_candidate"
    REQUALIFY = "requalify"
    RECONCILE = "reconcile"


@dataclass(frozen=True)
class Transition:
    scope: Scope
    state: WorkState
    reason: str
    followup: Followup = Followup.NONE
    candidate_ref: str | None = None
    checkpoint_required: bool = True


class CandidateOutcome(str, Enum):
    QUALIFICATION_REJECTED = "qualification_rejected"
    WRONG = "wrong"
    ACCEPTED = "accepted"
    ALREADY_SOLVED = "already_solved"
    AMBIGUOUS = "ambiguous"
    NOT_DELIVERED = "not_delivered"


@dataclass
class _Entry:
    challenge: Challenge
    state: WorkState = WorkState.READY
    reason: str = "initial_triage"
    approach_ref: str = "triage"
    approaches: set[str] = field(default_factory=lambda: {"triage"})
    approach_justifications: dict[str, str] = field(default_factory=dict)
    fingerprints: set[str] = field(default_factory=set)
    settled_candidates: set[str] = field(default_factory=set)
    pending_candidate: str | None = None
    attempts: int = 0
    bypasses: int = 0
    progress_revision: int = 0
    continuations: int = 0
    retries: int = 0
    repairs: int = 0
    ready_at: float | None = None
    blocked_on: str | None = None
    prerequisite_revision: str | None = None
    repair_next: bool = False
    failures: list[tuple[int, str, str]] = field(default_factory=list)


class Controller:
    """Call from the one existing harness loop. This class never runs another loop.

    ``now`` is supplied from one monotonic clock. Attempt budgets must be enforced
    by the model/tool adapters, which also own cancellation and resource release.
    The controller checks reported use and never creates or retries a side effect.
    """

    def __init__(self, *, started_at: float, limits: ControllerLimits | None = None):
        finite_number(started_at, "started_at")
        limits = limits if limits is not None else ControllerLimits()
        self.limits = limits
        self.deadline = started_at + limits.run_seconds
        finite_number(self.deadline, "deadline", positive=True)
        self._last_now = started_at
        self._entries: dict[Scope, _Entry] = {}
        self._current: dict[str, Scope] = {}
        self._blocked_subsystems: dict[str, str] = {}
        self._active: Attempt | None = None
        self._execution_token: int | None = None
        self._stop_reason: str | None = None
        self._idle_since: float | None = None
        self._serial = 0
        self._decisions = 0
        self._revision = 0
        self._models = 0
        self._tools = 0
        self._metrics = {
            name: 0
            for name in (
                "attempts",
                "continuations",
                "retries",
                "repairs",
                "candidates",
            )
        }
        self._lock = threading.RLock()

    def _time(self, now: float) -> None:
        finite_number(now, "now")
        if now < self._last_now:
            raise ValueError("controller requires a nondecreasing monotonic clock")
        self._last_now = now

    def _current_entry(self, scope: Scope) -> _Entry:
        if self._current.get(scope.challenge_id) != scope:
            raise ValueError("scope is not the current qualified material/instance")
        return self._entries[scope]

    def update_catalogue(self, challenges, *, now: float) -> None:
        """Upsert qualified metadata. Omission is NOT a deletion or a scope change."""
        batch = tuple(islice(challenges, self.limits.max_scopes + 1))
        if len(batch) > self.limits.max_scopes or not all(
            isinstance(item, Challenge) for item in batch
        ):
            raise ValueError("invalid or oversized catalogue update")
        if len({item.scope.challenge_id for item in batch}) != len(batch):
            raise ValueError("one current scope per challenge is required")
        with self._lock:
            self._time(now)
            if (
                len(set(self._entries) | {item.scope for item in batch})
                > self.limits.max_scopes
            ):
                raise ValueError(
                    "scope history capacity reached; owner must checkpoint and stop admission"
                )
            for item in batch:
                old = self._entries.get(item.scope)
                if old and old.challenge.authority_ref != item.authority_ref:
                    raise ValueError("authority changes require a new scoped identity")
                if old and self._current.get(item.scope.challenge_id) != item.scope:
                    raise ValueError(
                        "a retired scope cannot be reactivated by a stale catalogue"
                    )
            for item in batch:
                prior = self._current.get(item.scope.challenge_id)
                if prior != item.scope:
                    if prior is not None:
                        previous = self._entries[prior]
                        if previous.state not in {
                            WorkState.UNRESOLVED,
                            WorkState.AWAITING_CANDIDATE,
                        }:
                            previous.state = WorkState.SUPERSEDED
                    self._entries[item.scope] = _Entry(item)
                    self._current[item.scope.challenge_id] = item.scope
                    self._idle_since = None
                else:
                    self._entries[item.scope].challenge = item

    def _eligible(self, entry: _Entry, now: float) -> bool:
        if (
            self._current.get(entry.challenge.scope.challenge_id)
            != entry.challenge.scope
        ):
            return False
        if entry.state not in {WorkState.READY, WorkState.DEFERRED}:
            return False
        if any(
            other is not entry
            and other.challenge.scope.challenge_id == entry.challenge.scope.challenge_id
            and other.state in {WorkState.UNRESOLVED, WorkState.AWAITING_CANDIDATE}
            for other in self._entries.values()
        ):
            return False
        if entry.attempts >= self.limits.max_attempts_per_scope:
            return False
        if entry.blocked_on or entry.challenge.requires.intersection(
            self._blocked_subsystems
        ):
            return False
        if "model" in entry.challenge.requires and (
            self.limits.model_requests_per_attempt == 0
            or self._models >= self.limits.max_model_requests
        ):
            return False
        if "tools" in entry.challenge.requires and (
            self.limits.tool_calls_per_attempt == 0
            or self._tools >= self.limits.max_tool_calls
        ):
            return False
        return entry.state is WorkState.READY or (
            entry.ready_at is not None and entry.ready_at <= now
        )

    def next_action(self, *, now: float) -> Decision:
        with self._lock:
            self._time(now)
            self._decisions += 1
            if now >= self.deadline:
                self._stop_reason = self._stop_reason or "run_budget_exhausted"
            if self._serial >= self.limits.max_total_attempts and self._active is None:
                self._stop_reason = self._stop_reason or "admission_budget_exhausted"
            if self._stop_reason:
                return Decision(
                    DecisionKind.STOP,
                    self._stop_reason,
                    cancel_attempt_token=self._active.token if self._active else None,
                    checkpoint_required=True,
                    release_resources=True,
                )
            if self._active:
                if (
                    self._current.get(self._active.scope.challenge_id)
                    != self._active.scope
                ):
                    return Decision(
                        DecisionKind.WAIT,
                        "scope_changed_requires_cleanup",
                        cancel_attempt_token=self._active.token,
                        checkpoint_required=True,
                        release_resources=True,
                    )
                if now >= self._active.deadline:
                    return Decision(
                        DecisionKind.WAIT,
                        "attempt_deadline_requires_cleanup",
                        cancel_attempt_token=self._active.token,
                        checkpoint_required=True,
                        release_resources=True,
                    )
                return Decision(
                    DecisionKind.WAIT,
                    "attempt_in_flight",
                    wake_at=self._active.deadline,
                )
            records = [
                SchedulingRecord(
                    entry.challenge,
                    self._eligible(entry, now),
                    entry.attempts,
                    entry.bypasses,
                    entry.progress_revision,
                )
                for entry in self._entries.values()
            ]
            selected = select_challenge(
                records,
                policy=self.limits.selection,
                max_bypasses=self.limits.max_bypasses,
            )
            if selected:
                entry = self._entries[selected.challenge.scope]
                for record in records:
                    if record.eligible:
                        other = self._entries[record.challenge.scope]
                        other.bypasses = 0 if other is entry else other.bypasses + 1
                self._serial += 1
                budget = AttemptBudget(
                    min(self.limits.attempt_seconds, self.deadline - now),
                    min(
                        self.limits.model_requests_per_attempt,
                        max(0, self.limits.max_model_requests - self._models),
                    ),
                    min(
                        self.limits.tool_calls_per_attempt,
                        max(0, self.limits.max_tool_calls - self._tools),
                    ),
                )
                self._active = Attempt(
                    self._serial,
                    entry.challenge.scope,
                    entry.challenge.authority_ref,
                    entry.approach_ref,
                    now + budget.seconds,
                    budget,
                    entry.repair_next,
                )
                entry.repair_next = False
                entry.ready_at = None
                entry.state = WorkState.ACTIVE
                entry.attempts += 1
                self._metrics["attempts"] += 1
                self._idle_since = None
                return Decision(
                    DecisionKind.ATTEMPT, entry.reason, attempt=self._active
                )
            if self._idle_since is None:
                self._idle_since = now
            wakes = [
                entry.ready_at
                for entry in self._entries.values()
                if entry.state is WorkState.DEFERRED
                and entry.ready_at is not None
                and now < entry.ready_at < self.deadline
                and entry.attempts < self.limits.max_attempts_per_scope
                and not entry.blocked_on
                and not entry.challenge.requires.intersection(self._blocked_subsystems)
                and self._current.get(entry.challenge.scope.challenge_id)
                == entry.challenge.scope
            ]
            if not wakes and now - self._idle_since >= self.limits.idle_grace_seconds:
                self._stop_reason = "no_eligible_work_after_grace"
                return Decision(
                    DecisionKind.STOP,
                    self._stop_reason,
                    checkpoint_required=True,
                    release_resources=True,
                )
            wake = min(
                [now + self.limits.catalogue_poll_seconds, self.deadline, *wakes]
            )
            if not wakes:
                wake = min(wake, self._idle_since + self.limits.idle_grace_seconds)
            return Decision(
                DecisionKind.WAIT,
                "awaiting_work_or_prerequisite",
                wake_at=wake,
                refresh_catalogue=True,
            )

    def claim_attempt(self, attempt: Attempt) -> None:
        """Atomically bind an admitted lease to one executor until its completion report."""
        with self._lock:
            if self._active is not attempt or self._execution_token is not None:
                raise ValueError("attempt is not available for execution")
            self._execution_token = attempt.token

    def _observe(self, entry: _Entry, evidence: tuple[ProgressEvidence, ...]) -> bool:
        fresh = {
            item.fingerprint
            for item in evidence
            if item.confirmed and item.scope == entry.challenge.scope
        } - entry.fingerprints
        if not fresh:
            return False
        if len(entry.fingerprints | fresh) > 32 * self.limits.max_attempts_per_scope:
            raise ValueError("evidence reference capacity reached")
        entry.fingerprints.update(fresh)
        self._revision += 1
        entry.progress_revision = self._revision
        return True

    def finish_attempt(
        self, token: int, report: AttemptReport, *, now: float
    ) -> Transition:
        with self._lock:
            self._time(now)
            if (
                type(token) is not int
                or self._active is None
                or self._active.token != token
                or self._active.scope != report.scope
            ):
                raise ValueError("report does not own the active attempt")
            attempt = self._active
            entry = self._entries[attempt.scope]
            self._active = None
            self._execution_token = None
            self._models += report.model_requests
            self._tools += report.tool_calls
            entry.state = WorkState.DEFERRED
            entry.ready_at = None
            current = self._current.get(attempt.scope.challenge_id) == attempt.scope
            stopped = self._stop_reason is not None or now >= self.deadline
            over_budget = (
                report.model_requests > attempt.budget.model_requests
                or report.tool_calls > attempt.budget.tool_calls
            )
            if report.failure:
                entry.failures.append(
                    (attempt.token, attempt.approach_ref, report.failure.kind.value)
                )
                decision = retry_decision(
                    report.failure,
                    transient_retries=entry.retries,
                    repairs=entry.repairs,
                    remaining_seconds=max(0, self.deadline - now),
                    limits=self.limits.retry,
                )
                entry.reason = decision.reason
                if decision.action is RetryAction.RECONCILE:
                    entry.state = WorkState.UNRESOLVED
                    return Transition(
                        attempt.scope, entry.state, entry.reason, Followup.RECONCILE
                    )
                if decision.action is RetryAction.REQUALIFY:
                    if report.failure.operation is Operation.INSTANCE_MUTATION:
                        entry.state = WorkState.UNRESOLVED
                    entry.prerequisite_revision = (
                        entry.challenge.scope.instance_id
                        or entry.challenge.scope.material_id
                    )
                    return Transition(
                        attempt.scope, entry.state, entry.reason, Followup.REQUALIFY
                    )
                if decision.action is RetryAction.BLOCK_SUBSYSTEM:
                    failure = report.failure
                    self._blocked_subsystems[failure.subsystem] = (
                        failure.configuration_revision
                    )
                    entry.blocked_on = failure.subsystem
                elif decision.action is RetryAction.STOP_OPERATION:
                    entry.state = WorkState.TERMINAL
                elif current and not stopped and not over_budget:
                    if decision.action is RetryAction.RETRY:
                        entry.retries += 1
                        self._metrics["retries"] += 1
                        entry.ready_at = now + decision.delay_seconds
                    elif decision.action is RetryAction.REPAIR:
                        entry.repairs += 1
                        self._metrics["repairs"] += 1
                        entry.repair_next = True
                        entry.state = WorkState.READY
            elif not current:
                entry.state, entry.reason = WorkState.SUPERSEDED, "scope_changed"
            elif over_budget or now >= attempt.deadline:
                entry.reason = "attempt_budget_exceeded"
            elif stopped:
                entry.reason = "stopped_checkpoint_only"
                entry.pending_candidate = report.candidate_ref
            else:
                fresh = self._observe(entry, report.evidence)
                if report.candidate_ref:
                    if report.candidate_ref in entry.settled_candidates:
                        entry.reason = "settled_candidate_duplicate"
                    else:
                        entry.pending_candidate = report.candidate_ref
                        entry.state = WorkState.AWAITING_CANDIDATE
                        entry.reason = "candidate_needs_owner_qualification"
                        self._metrics["candidates"] += 1
                        return Transition(
                            attempt.scope,
                            entry.state,
                            entry.reason,
                            Followup.QUALIFY_CANDIDATE,
                            report.candidate_ref,
                        )
                elif (
                    fresh
                    and entry.continuations < self.limits.max_continuations_per_approach
                ):
                    entry.continuations += 1
                    self._metrics["continuations"] += 1
                    entry.state, entry.reason = (
                        WorkState.READY,
                        "new_confirmed_evidence",
                    )
                else:
                    entry.reason = (
                        "continuation_allowance_exhausted"
                        if fresh
                        else "no_new_evidence"
                    )
                    if not fresh:
                        entry.failures.append(
                            (attempt.token, attempt.approach_ref, "no_progress")
                        )
            if entry.attempts >= self.limits.max_attempts_per_scope and entry.state in {
                WorkState.READY,
                WorkState.DEFERRED,
            }:
                entry.state, entry.reason, entry.ready_at = (
                    WorkState.TERMINAL,
                    "attempt_allowance_exhausted",
                    None,
                )
            return Transition(attempt.scope, entry.state, entry.reason)

    def propose_approach(
        self, scope: Scope, approach_ref: str, justification_ref: str
    ) -> bool:
        """A trusted, justified changed experiment may revive stalled work, never an effect."""
        bounded_ref(approach_ref, "approach_ref")
        bounded_ref(justification_ref, "justification_ref")
        with self._lock:
            entry = self._current_entry(scope)
            if (
                entry.state is not WorkState.DEFERRED
                or entry.blocked_on
                or entry.prerequisite_revision
            ):
                return False
            if (
                entry.ready_at is not None
                or entry.attempts >= self.limits.max_attempts_per_scope
            ):
                return False
            if (
                approach_ref in entry.approaches
                or len(entry.approaches) >= self.limits.max_attempts_per_scope
            ):
                return False
            entry.approaches.add(approach_ref)
            entry.approach_justifications[approach_ref] = justification_ref
            entry.approach_ref = approach_ref
            entry.continuations = 0
            entry.state, entry.reason = WorkState.READY, "justified_changed_approach"
            self._idle_since = None
            return True

    def observe_evidence(
        self, scope: Scope, evidence: tuple[ProgressEvidence, ...]
    ) -> bool:
        AttemptReport(
            scope, evidence=evidence
        )  # Validate the bounded transport record.
        with self._lock:
            entry = self._current_entry(scope)
            if (
                entry.state is not WorkState.DEFERRED
                or entry.reason != "no_new_evidence"
            ):
                return False
            if (
                entry.attempts >= self.limits.max_attempts_per_scope
                or entry.continuations >= self.limits.max_continuations_per_approach
            ):
                return False
            if not self._observe(entry, evidence):
                return False
            entry.continuations += 1
            self._metrics["continuations"] += 1
            entry.state, entry.reason = WorkState.READY, "new_confirmed_evidence"
            self._idle_since = None
            return True

    def update_configuration(self, subsystem: str, revision: str) -> bool:
        bounded_ref(subsystem, "subsystem")
        bounded_ref(revision, "revision")
        with self._lock:
            prior = self._blocked_subsystems.get(subsystem)
            if prior is None or prior == revision:
                return False
            del self._blocked_subsystems[subsystem]
            for entry in self._entries.values():
                if entry.blocked_on == subsystem:
                    entry.blocked_on = None
                    if entry.state is WorkState.DEFERRED:
                        entry.state, entry.reason = (
                            WorkState.READY,
                            "configuration_changed",
                        )
            self._idle_since = None
            return True

    def requalified(self, scope: Scope, *, revision: str) -> bool:
        """Called only after Jerome resolves the prerequisite; never performs a mutation."""
        bounded_ref(revision, "revision")
        with self._lock:
            entry = self._current_entry(scope)
            if (
                entry.state is not WorkState.DEFERRED
                or entry.prerequisite_revision is None
            ):
                return False
            if (
                entry.prerequisite_revision == revision
                or entry.attempts >= self.limits.max_attempts_per_scope
            ):
                return False
            entry.prerequisite_revision = None
            entry.state, entry.reason = WorkState.READY, "owner_requalified"
            self._idle_since = None
            return True

    def resolve_candidate(
        self, scope: Scope, candidate_ref: str, outcome: CandidateOutcome
    ) -> Transition:
        """Consume Richard/Jerome's definitive or uncertain verdict; never decide acceptance."""
        _fingerprint(candidate_ref)
        if not isinstance(outcome, CandidateOutcome):
            raise ValueError("candidate outcome must be classified")
        with self._lock:
            entry = self._entries.get(scope)
            if entry is None or entry.pending_candidate != candidate_ref:
                raise ValueError("no matching scoped candidate handoff")
            if entry.state not in {WorkState.AWAITING_CANDIDATE, WorkState.UNRESOLVED}:
                raise ValueError("candidate is not awaiting an owner decision")
            if (
                entry.state is WorkState.UNRESOLVED
                and outcome is CandidateOutcome.QUALIFICATION_REJECTED
            ):
                raise ValueError("qualification cannot settle an unresolved submission")
            if outcome is CandidateOutcome.AMBIGUOUS:
                entry.state, entry.reason = (
                    WorkState.UNRESOLVED,
                    "unresolved_submission",
                )
                return Transition(
                    scope, entry.state, entry.reason, Followup.RECONCILE, candidate_ref
                )
            if outcome is CandidateOutcome.ALREADY_SOLVED:
                entry.reason = "account_history_requires_owner_verification"
                return Transition(
                    scope, entry.state, entry.reason, candidate_ref=candidate_ref
                )
            entry.pending_candidate = None
            if outcome in {CandidateOutcome.WRONG, CandidateOutcome.ACCEPTED}:
                entry.settled_candidates.add(candidate_ref)
            entry.state = (
                WorkState.TERMINAL
                if outcome is CandidateOutcome.ACCEPTED
                else WorkState.DEFERRED
            )
            entry.reason = outcome.value
            return Transition(scope, entry.state, entry.reason)

    def reconciled_effect(self, scope: Scope, *, resolution_ref: str) -> Transition:
        """Owner confirms an effect without a candidate. No automatic replay follows."""
        bounded_ref(resolution_ref, "resolution_ref")
        with self._lock:
            entry = self._entries.get(scope)
            if (
                entry is None
                or entry.state is not WorkState.UNRESOLVED
                or entry.pending_candidate
            ):
                raise ValueError(
                    "use the matching owner path for this unresolved effect"
                )
            entry.state, entry.reason = WorkState.DEFERRED, "owner_reconciled_effect"
            entry.prerequisite_revision = None
            return Transition(scope, entry.state, entry.reason)

    def cancel(self) -> None:
        with self._lock:
            self._stop_reason = self._stop_reason or "cancelled"

    def snapshot(self) -> dict:
        """Private controller checkpoint input for Richard; NOT /work/results.json."""
        with self._lock:
            return {
                "stop_reason": self._stop_reason,
                "active_attempt_token": self._active.token if self._active else None,
                "active_execution_token": self._execution_token,
                "metrics": {
                    **self._metrics,
                    "decisions": self._decisions,
                    "model_requests": self._models,
                    "tool_calls": self._tools,
                    "scopes_attempted": sum(
                        entry.attempts > 0 for entry in self._entries.values()
                    ),
                },
                "work": tuple(
                    {
                        "scope": entry.challenge.scope,
                        "state": entry.state.value,
                        "reason": entry.reason,
                        "attempts": entry.attempts,
                        "approach_ref": entry.approach_ref,
                        "approach_justifications": tuple(
                            sorted(entry.approach_justifications.items())
                        ),
                        "ready_at": entry.ready_at,
                        "pending_candidate": entry.pending_candidate,
                        "progress_fingerprints": tuple(sorted(entry.fingerprints)),
                        "failures": tuple(entry.failures),
                        "retries": entry.retries,
                        "repairs": entry.repairs,
                        "continuations": entry.continuations,
                    }
                    for entry in sorted(
                        self._entries.values(),
                        key=lambda entry: entry.challenge.scope.sort_key,
                    )
                ),
            }
