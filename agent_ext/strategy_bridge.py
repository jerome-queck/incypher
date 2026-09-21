"""Execute one admitted attempt through the existing Brain and shared records.

The integration owner supplies qualified scope and evidence/ledger callbacks.
There is one call to Brain.solve, no outer solver loop, and one authorized
submission callback. This module does not replace the inherited entrypoint.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Callable, Mapping
from typing import Protocol

from .contracts import (
    Budget,
    Candidate,
    ChallengeScope,
    FailureCategory,
    NextAction,
    SubmissionResult,
    SubmissionStatus,
    ToolResult,
)
from .controller import (
    Attempt,
    AttemptReport,
    CandidateOutcome,
    Controller,
    Decision,
    Followup,
    ProgressEvidence,
)
from .retry_policy import Failure, FailureKind, Operation
from .scheduler import Challenge, bounded_ref, finite_number


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def challenge_from_shared(scope: ChallengeScope, authority_ref: str) -> Challenge:
    """Keep material/instance identity stable across parent attempts; never parse a prompt."""
    from .scheduler import Scope

    if not isinstance(scope, ChallengeScope):
        raise ValueError("qualified ChallengeScope required")
    if type(scope.challenge_id) is not int or scope.challenge_id <= 0:
        raise ValueError("challenge ID must be a positive integer")
    bounded_ref(scope.attempt_id, "parent attempt ID")
    for value in (scope.material_ref, scope.instance_generation):
        if value is not None and (
            not isinstance(value, str) or not value or len(value) > 4096
        ):
            raise ValueError("material/instance reference must be bounded and nonempty")
    if scope.material_ref is None:
        raise ValueError("qualified material reference required")
    return Challenge(
        Scope(
            str(scope.challenge_id),
            _digest(scope.material_ref),
            _digest(scope.instance_generation) if scope.instance_generation else None,
        ),
        authority_ref,
        requires=frozenset({"model"}),
    )


def action_from_decision(decision: Decision) -> NextAction:
    """Project a controller decision into the merged team contract."""
    arguments = {
        "wake_at": decision.wake_at,
        "refresh_catalogue": decision.refresh_catalogue,
        "cancel_attempt_token": decision.cancel_attempt_token,
        "checkpoint_required": decision.checkpoint_required,
        "release_resources": decision.release_resources,
    }
    if decision.attempt is not None:
        attempt = decision.attempt
        arguments.update(
            token=attempt.token,
            scope=attempt.scope,
            authority_ref=attempt.authority_ref,
            approach_ref=attempt.approach_ref,
            deadline=attempt.deadline,
            model_requests=attempt.budget.model_requests,
            tool_calls=attempt.budget.tool_calls,
            repair=attempt.repair,
        )
    return NextAction(decision.kind.value, arguments, decision.reason)


def submission_from_verdict(intent_id: str, verdict) -> SubmissionResult:
    """Unknown/absent/malformed callback results are uncertain, never negative proof."""
    bounded_ref(intent_id, "intent ID")
    value = verdict.get("status") if isinstance(verdict, Mapping) else None
    try:
        status = SubmissionStatus(value)
    except (ValueError, TypeError):
        status = SubmissionStatus.UNCERTAIN
    definitive = status in {
        SubmissionStatus.CORRECT,
        SubmissionStatus.INCORRECT,
        SubmissionStatus.ALREADY_SOLVED,
    }
    error = None
    if status is SubmissionStatus.RATE_LIMITED:
        error = FailureCategory.RATE_LIMITED
    elif not definitive:
        error = FailureCategory.UNKNOWN
    return SubmissionResult(intent_id, status, definitive, error)


def outcome_from_submission(result: SubmissionResult) -> CandidateOutcome:
    if not isinstance(result, SubmissionResult):
        raise ValueError("shared SubmissionResult required")
    if (
        not isinstance(result.status, SubmissionStatus)
        or type(result.definitive) is not bool
    ):
        raise ValueError("submission result must be classified")
    return {
        SubmissionStatus.CORRECT: CandidateOutcome.ACCEPTED,
        SubmissionStatus.INCORRECT: CandidateOutcome.WRONG,
        SubmissionStatus.ALREADY_SOLVED: CandidateOutcome.ALREADY_SOLVED,
    }.get(result.status, CandidateOutcome.AMBIGUOUS)


def failure_from_tool(result: ToolResult) -> Failure | None:
    """Use shared classifications conservatively; a resource limit alone is not OOM."""
    if result.error is None:
        return None
    if not isinstance(result.error, FailureCategory):
        raise ValueError("tool error must use the shared FailureCategory")
    if result.error in {FailureCategory.AUTHENTICATION, FailureCategory.CONFIGURATION}:
        kind = (
            FailureKind.AUTHENTICATION
            if result.error is FailureCategory.AUTHENTICATION
            else FailureKind.CONFIGURATION
        )
        # The shared record has no configuration revision. Block the unreported
        # revision until its owner explicitly supplies a changed one.
        return Failure(
            kind, Operation.TOOL, subsystem="tools", configuration_revision="unreported"
        )
    kind = {
        FailureCategory.TIMEOUT: FailureKind.TOOL_TIMEOUT,
        FailureCategory.RATE_LIMITED: FailureKind.RATE_LIMIT,
    }.get(result.error, FailureKind.UNKNOWN)
    return Failure(kind, Operation.TOOL)


class StrategyOwners(Protocol):
    """Elson-side callbacks using merged records; implementations belong to owners.

    observe() classifies Aidan's result and supplies Richard-confirmed evidence.
    reserve_intent() and checkpoint() must persist the unique intent before send.
    checkpoint() projects private state; it must not create a second official writer.
    """

    def observe(
        self, scope: ChallengeScope, action: NextAction, output: str, seconds: float
    ) -> tuple[ToolResult, tuple[ProgressEvidence, ...]]: ...

    def qualify(self, scope: ChallengeScope, candidate: Candidate) -> bool: ...

    def reserve_intent(self, scope: ChallengeScope, candidate: Candidate) -> str: ...

    def record_submission(
        self, scope: ChallengeScope, result: SubmissionResult
    ) -> None: ...

    def checkpoint(self, scope: ChallengeScope, state: dict) -> None: ...

    def release(self, scope: ChallengeScope) -> None: ...


class _AttemptStopped(Exception):
    pass


class _CandidateReady(Exception):
    """Return control to qualification before any external submission occurs."""


def _default_model_failure(exc: Exception) -> Failure:
    from requests import HTTPError

    from .adapters import ConfigurationError

    kind = FailureKind.UNKNOWN
    if isinstance(exc, ConfigurationError):
        kind = FailureKind.CONFIGURATION
    elif (
        isinstance(exc, HTTPError)
        and exc.response is not None
        and exc.response.status_code in {401, 403}
    ):
        kind = FailureKind.AUTHENTICATION
    if kind in {FailureKind.CONFIGURATION, FailureKind.AUTHENTICATION}:
        return Failure(
            kind,
            Operation.MODEL,
            subsystem="model",
            configuration_revision="unreported",
        )
    return Failure(kind, Operation.MODEL)


class BrainAttempt:
    """One-shot execution adapter for an already admitted, qualified attempt.

    Callbacks remain synchronous: admission/deadline checks cannot interrupt a
    call already running. The integration owner must supply bounded callbacks.
    Nothing automatically instantiates this adapter in the inherited main loop.
    """

    def __init__(
        self,
        controller: Controller,
        attempt: Attempt,
        scope: ChallengeScope,
        budget: Budget,
        owners: StrategyOwners,
        *,
        clock: Callable[[], float] = time.monotonic,
        cancelled: Callable[[], bool] = lambda: False,
        classify_model_failure: Callable[[Exception], Failure] | None = None,
    ):
        qualified = challenge_from_shared(scope, attempt.authority_ref)
        if qualified.scope != attempt.scope:
            raise ValueError("shared scope does not match admitted material/instance")
        if not isinstance(budget, Budget):
            raise ValueError("shared Budget required")
        for value in (budget.steps_remaining, budget.submissions_remaining):
            if type(value) is not int or value < 0:
                raise ValueError("shared allowances must be nonnegative integers")
        deadline = attempt.deadline
        if budget.deadline_monotonic is not None:
            finite_number(budget.deadline_monotonic, "shared deadline")
            deadline = min(deadline, budget.deadline_monotonic)
        self.controller, self.attempt, self.scope = controller, attempt, scope
        self.budget, self.owners = budget, owners
        self.clock, self.cancelled = clock, cancelled
        self.classify_model_failure = classify_model_failure
        self.deadline = min(deadline, controller.deadline)
        self.max_models = min(attempt.budget.model_requests, budget.steps_remaining)
        self.models = self.tools = 0
        self.evidence: dict[str, ProgressEvidence] = {}
        self.candidate: Candidate | None = None
        self.failure: Failure | None = None
        self.stop_reason: str | None = None
        self._used = False
        self._finished = False
        self._commands: set[str] = set()

    def _guard(self) -> None:
        now = self.clock()
        finite_number(now, "clock")
        if self.cancelled():
            self.controller.cancel()
        with self.controller._lock:
            if not self._finished and self.controller._active is not self.attempt:
                self.stop_reason = "attempt_ownership_changed"
            elif self.controller._stop_reason is not None:
                self.stop_reason = "cancelled_or_stopped"
            elif (
                self.controller._current.get(self.attempt.scope.challenge_id)
                != self.attempt.scope
            ):
                self.stop_reason = "scope_changed"
            elif now >= self.deadline:
                self.stop_reason = "attempt_deadline"
        if self.stop_reason:
            raise _AttemptStopped(self.stop_reason)

    def _model(self, invoke, messages):
        self._guard()
        if self.models >= self.max_models:
            self.stop_reason = "model_allowance_exhausted"
            raise _AttemptStopped(self.stop_reason)
        self.models += 1
        try:
            response = invoke(messages)
        except Exception as exc:
            self.failure = Failure(FailureKind.UNKNOWN, Operation.MODEL)
            failure = (
                self.classify_model_failure(exc)
                if self.classify_model_failure
                else _default_model_failure(exc)
            )
            if (
                not isinstance(failure, Failure)
                or failure.operation is not Operation.MODEL
            ):
                failure = Failure(FailureKind.UNKNOWN, Operation.MODEL)
            self.failure = failure
            # Brain catches model exceptions. Keep transport text/credentials out of its result.
            raise _AttemptStopped("classified_model_failure") from None
        if isinstance(response, Mapping) and response.get("refusal"):
            self.failure = Failure(FailureKind.SAFETY_REFUSAL, Operation.MODEL)
            raise _AttemptStopped("provider_refusal")
        self._guard()
        return response

    def _tool(self, invoke, command):
        self._guard()
        if not isinstance(command, str) or not command.strip():
            self.failure = Failure(FailureKind.MALFORMED_REQUEST, Operation.TOOL)
            raise _AttemptStopped("malformed_tool_request")
        if self.tools >= self.attempt.budget.tool_calls:
            self.stop_reason = "tool_allowance_exhausted"
            raise _AttemptStopped(self.stop_reason)
        command_ref = _digest(command)
        if command_ref in self._commands:
            self.failure = Failure(FailureKind.NO_PROGRESS, Operation.TOOL)
            raise _AttemptStopped("identical_tool_call_requires_new_approach")
        self._commands.add(command_ref)
        self.tools += 1
        started = self.clock()
        output = invoke(command)
        duration = self.clock() - started
        finite_number(duration, "tool duration")
        if not isinstance(output, str):
            raise _AttemptStopped("malformed_tool_output")
        action = NextAction("run_bash", {"command": command}, "admitted_tool_call")
        observation, progress = self.owners.observe(
            self.scope, action, output, duration
        )
        if not isinstance(observation, ToolResult) or not isinstance(
            observation.excerpt, str
        ):
            raise ValueError("owner must return a shared ToolResult")
        if len(observation.excerpt) > 12000:
            raise ValueError("owner observation excerpt exceeds Brain allowance")
        AttemptReport(self.attempt.scope, evidence=progress)
        for item in progress:
            if item.confirmed and item.scope == self.attempt.scope:
                self.evidence[item.fingerprint] = item
        if len(self.evidence) > 32:
            raise ValueError("attempt evidence allowance exceeded")
        if observation.error is not None:
            if observation.error is FailureCategory.CANCELLED:
                self.controller.cancel()
            self.failure = failure_from_tool(observation)
            raise _AttemptStopped("classified_tool_failure")
        self._guard()
        return observation.excerpt

    def _capture_candidate(self, value):
        self._guard()
        if self.budget.submissions_remaining == 0:
            raise _AttemptStopped("submission_allowance_exhausted")
        if not isinstance(value, str) or not value or len(value) > 4096:
            raise _AttemptStopped("malformed_candidate")
        self.candidate = Candidate(value, tuple(sorted(self.evidence)))
        # No transport call happens inside Brain's submit callback. Unwind its
        # single solve loop, then apply the controller and owner's candidate gate.
        raise _CandidateReady()

    def _submit_candidate(self, submit_flag, transition) -> dict:
        candidate = self.candidate
        candidate_ref = transition.candidate_ref
        self._guard()
        qualified = self.owners.qualify(self.scope, candidate)
        if type(qualified) is not bool:
            raise ValueError(
                "candidate qualification must be an explicit owner verdict"
            )
        if not qualified:
            self.controller.resolve_candidate(
                self.attempt.scope,
                candidate_ref,
                CandidateOutcome.QUALIFICATION_REJECTED,
            )
            return {
                "solved": False,
                "steps": self.models,
                "final": "qualification_rejected",
            }
        self._guard()
        try:
            intent_id = self.owners.reserve_intent(self.scope, candidate)
            bounded_ref(intent_id, "intent ID")
            self.owners.checkpoint(self.scope, self.controller.snapshot())
            self._guard()
            try:
                result = submission_from_verdict(
                    intent_id, submit_flag(candidate.value)
                )
            except Exception:
                result = SubmissionResult(
                    intent_id,
                    SubmissionStatus.UNCERTAIN,
                    False,
                    FailureCategory.UNKNOWN,
                )
            self.owners.record_submission(self.scope, result)
        except Exception:
            self.controller.resolve_candidate(
                self.attempt.scope, candidate_ref, CandidateOutcome.AMBIGUOUS
            )
            return {
                "solved": False,
                "steps": self.models,
                "error": "intent_requires_reconciliation",
            }
        except BaseException:
            # Interrupts can arrive after the callback applies its side effect.
            # Preserve the intent before propagating cancellation to the harness.
            self.controller.cancel()
            self.controller.resolve_candidate(
                self.attempt.scope, candidate_ref, CandidateOutcome.AMBIGUOUS
            )
            raise
        self.controller.resolve_candidate(
            self.attempt.scope, candidate_ref, outcome_from_submission(result)
        )
        solved = result.status in {
            SubmissionStatus.CORRECT,
            SubmissionStatus.ALREADY_SOLVED,
        }
        projection = {
            "solved": solved,
            "steps": self.models,
            "verdict": {"status": result.status.value},
        }
        if solved:
            # Preserve the inherited return contract; only its writer handles this value.
            projection["flag"] = candidate.value
        elif not result.definitive:
            projection["error"] = "intent_requires_reconciliation"
        return projection

    def run(self, prompt: str, *, run_bash, submit_flag) -> dict:
        """Call the actual Brain once using synthetic or authorized existing callbacks."""
        from brain import Brain

        if self._used:
            raise ValueError("an admitted Brain attempt can be executed only once")
        self.controller.claim_attempt(self.attempt)
        self._used = True
        execution = self

        class AdmittedBrain(Brain):
            def _chat(self, messages):
                return execution._model(super()._chat, messages)

            def _invalid_tool_arguments(self, name):
                execution.failure = Failure(FailureKind.MALFORMED_REQUEST, Operation.TOOL)
                raise _AttemptStopped("malformed_tool_request")

        agent = None
        projection = {"solved": False, "steps": 0}
        try:
            try:
                self._guard()
                agent = AdmittedBrain(
                    lambda command: self._tool(run_bash, command),
                    self._capture_candidate,
                    max_steps=self.max_models,
                    verbose=False,
                )
                agent.solve(prompt)
            except _CandidateReady:
                pass
            except _AttemptStopped as exc:
                self.stop_reason = self.stop_reason or str(exc)
            except Exception:
                self.failure = self.failure or Failure(
                    FailureKind.UNKNOWN, Operation.TOOL
                )
                self.stop_reason = "attempt_adapter_failure"
            transition = self.controller.finish_attempt(
                self.attempt.token,
                AttemptReport(
                    self.attempt.scope,
                    evidence=tuple(self.evidence.values())[:32],
                    candidate_ref=_digest(self.candidate.value)
                    if self.candidate
                    else None,
                    failure=self.failure,
                    model_requests=self.models,
                    tool_calls=self.tools,
                ),
                now=self.clock(),
            )
            self._finished = True
            projection = {
                "solved": False,
                "steps": self.models,
                "final": self.stop_reason or transition.reason,
            }
            if transition.followup is Followup.QUALIFY_CANDIDATE:
                try:
                    projection = self._submit_candidate(submit_flag, transition)
                except Exception:
                    # Qualification failure/cancellation before intent reservation:
                    # preserve the pending handoff; do not manufacture an acceptance.
                    projection["error"] = "candidate_handoff_incomplete"
            return projection
        except BaseException:
            self.controller.cancel()
            raise
        finally:
            if not self._finished:
                self.controller.cancel()
                with self.controller._lock:
                    if self.controller._active is self.attempt:
                        self.controller.finish_attempt(
                            self.attempt.token,
                            AttemptReport(
                                self.attempt.scope,
                                model_requests=self.models,
                                tool_calls=self.tools,
                            ),
                            now=self.controller._last_now,
                        )
            for name, operation in (
                (
                    "model_session",
                    lambda: agent.s.close() if agent is not None else None,
                ),
                ("resource_release", lambda: self.owners.release(self.scope)),
                (
                    "checkpoint",
                    lambda: self.owners.checkpoint(
                        self.scope, self.controller.snapshot()
                    ),
                ),
            ):
                try:
                    operation()
                except Exception:
                    projection.setdefault("cleanup_errors", []).append(name)
