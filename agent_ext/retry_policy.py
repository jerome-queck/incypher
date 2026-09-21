"""Bounded retry decisions and a cancellable wait; never executes an operation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum

from .scheduler import bounded_ref, finite_number


class Operation(str, Enum):
    READ = "read"
    MODEL = "model"
    TOOL = "tool"
    INSTANCE_MUTATION = "instance_mutation"
    SUBMISSION = "submission"


class FailureKind(str, Enum):
    AUTHENTICATION = "authentication"
    CONFIGURATION = "configuration"
    TRANSIENT = "transient"
    RATE_LIMIT = "rate_limit"
    MALFORMED_REQUEST = "malformed_request"
    TOOL_TIMEOUT = "tool_timeout"
    TOOL_OOM = "tool_oom"
    STALE_INSTANCE = "stale_instance"
    WRONG_CANDIDATE = "wrong_candidate"
    AMBIGUOUS_SUBMISSION = "ambiguous_submission"
    NO_PROGRESS = "no_progress"
    SAFETY_REFUSAL = "safety_refusal"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Failure:
    kind: FailureKind
    operation: Operation
    documented_transient: bool = False
    retry_after: float | None = None
    adapter_retried: bool = False
    subsystem: str | None = None
    configuration_revision: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, FailureKind) or not isinstance(
            self.operation, Operation
        ):
            raise ValueError("failure kind and operation must be classified enums")
        if (
            type(self.documented_transient) is not bool
            or type(self.adapter_retried) is not bool
        ):
            raise ValueError("retry flags must be booleans")
        if self.retry_after is not None:
            finite_number(self.retry_after, "retry_after")
        for name in ("subsystem", "configuration_revision"):
            if getattr(self, name) is not None:
                bounded_ref(getattr(self, name), name)
        if self.kind in {FailureKind.AUTHENTICATION, FailureKind.CONFIGURATION}:
            if self.subsystem is None or self.configuration_revision is None:
                raise ValueError(
                    "configuration failures require a subsystem and sanitized revision"
                )


class RetryAction(str, Enum):
    RETRY = "retry"
    REPAIR = "repair"
    CHANGE_APPROACH = "change_approach"
    BLOCK_SUBSYSTEM = "block_subsystem"
    REQUALIFY = "requalify"
    RECONCILE = "reconcile"
    RECORD_WRONG = "record_wrong"
    STOP_OPERATION = "stop_operation"
    DEFER = "defer"


@dataclass(frozen=True)
class RetryDecision:
    action: RetryAction
    reason: str
    delay_seconds: float = 0


@dataclass(frozen=True)
class RetryLimits:
    max_transient_retries: int = 2
    max_repairs: int = 1
    base_delay_seconds: float = 1
    max_backoff_seconds: float = 8

    def __post_init__(self) -> None:
        for name in ("max_transient_retries", "max_repairs"):
            value = getattr(self, name)
            if type(value) is not int or not 0 <= value <= 100:
                raise ValueError(f"{name} must be an integer between 0 and 100")
        finite_number(self.base_delay_seconds, "base_delay_seconds", positive=True)
        finite_number(self.max_backoff_seconds, "max_backoff_seconds", positive=True)
        if self.max_backoff_seconds < self.base_delay_seconds:
            raise ValueError("maximum backoff must cover the base delay")


def retry_decision(
    failure: Failure,
    *,
    transient_retries: int = 0,
    repairs: int = 0,
    remaining_seconds: float,
    limits: RetryLimits | None = None,
) -> RetryDecision:
    limits = limits if limits is not None else RetryLimits()
    for name, value in (("transient_retries", transient_retries), ("repairs", repairs)):
        if type(value) is not int or value < 0:
            raise ValueError(f"{name} must be a nonnegative integer")
    finite_number(remaining_seconds, "remaining_seconds")
    kind = failure.kind
    if kind is FailureKind.SAFETY_REFUSAL:
        return RetryDecision(RetryAction.STOP_OPERATION, "provider_refusal")
    if kind is FailureKind.AMBIGUOUS_SUBMISSION:
        return RetryDecision(RetryAction.RECONCILE, "unresolved_submission")
    if kind is FailureKind.WRONG_CANDIDATE:
        return RetryDecision(RetryAction.RECORD_WRONG, "settled_wrong_candidate")
    # Neither a rate-limit label nor a retry-after value proves a mutation was not applied.
    if failure.operation is Operation.SUBMISSION:
        return RetryDecision(
            RetryAction.RECONCILE, "submission_requires_owner_reconciliation"
        )
    if failure.operation is Operation.INSTANCE_MUTATION:
        return RetryDecision(RetryAction.REQUALIFY, "instance_mutation_requires_owner")
    if kind in {FailureKind.AUTHENTICATION, FailureKind.CONFIGURATION}:
        return RetryDecision(RetryAction.BLOCK_SUBSYSTEM, "unchanged_configuration")
    if kind is FailureKind.STALE_INSTANCE:
        return RetryDecision(RetryAction.REQUALIFY, "stale_instance")
    if remaining_seconds <= 0:
        return RetryDecision(RetryAction.DEFER, "run_budget_exhausted")
    if failure.adapter_retried:
        return RetryDecision(RetryAction.DEFER, "adapter_already_owns_retries")
    if kind in {FailureKind.TRANSIENT, FailureKind.RATE_LIMIT}:
        if not failure.documented_transient or failure.operation not in {
            Operation.READ,
            Operation.MODEL,
        }:
            return RetryDecision(RetryAction.DEFER, "transience_not_established")
        if transient_retries >= limits.max_transient_retries:
            return RetryDecision(RetryAction.DEFER, "retry_allowance_exhausted")
        delay = min(
            limits.max_backoff_seconds, limits.base_delay_seconds * 2**transient_retries
        )
        delay = max(delay, failure.retry_after or 0)
        if delay >= remaining_seconds:
            return RetryDecision(RetryAction.DEFER, "retry_guidance_exceeds_budget")
        return RetryDecision(RetryAction.RETRY, "documented_transient", delay)
    if kind is FailureKind.MALFORMED_REQUEST:
        if repairs < limits.max_repairs:
            return RetryDecision(RetryAction.REPAIR, "bounded_same_authority_repair")
        return RetryDecision(RetryAction.CHANGE_APPROACH, "repair_allowance_exhausted")
    if kind in {
        FailureKind.TOOL_TIMEOUT,
        FailureKind.TOOL_OOM,
        FailureKind.NO_PROGRESS,
    }:
        return RetryDecision(
            RetryAction.CHANGE_APPROACH, "different_experiment_required"
        )
    return RetryDecision(RetryAction.DEFER, "unclassified_failure")


class WaitOutcome(str, Enum):
    READY = "ready"
    CANCELLED = "cancelled"
    DEADLINE = "deadline"


async def wait_for_retry(
    delay_seconds: float, *, cancellation: asyncio.Event, remaining_seconds: float
) -> WaitOutcome:
    """Wait only. Caller cancellation propagates and both child tasks are drained."""
    finite_number(delay_seconds, "delay_seconds")
    finite_number(remaining_seconds, "remaining_seconds")
    if cancellation.is_set():
        return WaitOutcome.CANCELLED
    if remaining_seconds == 0:
        return WaitOutcome.DEADLINE
    timer = asyncio.create_task(asyncio.sleep(min(delay_seconds, remaining_seconds)))
    cancelled = asyncio.create_task(cancellation.wait())
    try:
        await asyncio.wait({timer, cancelled}, return_when=asyncio.FIRST_COMPLETED)
        if cancellation.is_set():
            return WaitOutcome.CANCELLED
        return (
            WaitOutcome.DEADLINE
            if delay_seconds >= remaining_seconds
            else WaitOutcome.READY
        )
    finally:
        for task in (timer, cancelled):
            task.cancel()
        await asyncio.gather(timer, cancelled, return_exceptions=True)
