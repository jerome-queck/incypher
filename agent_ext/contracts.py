"""Pure semantic records for team-owned modules behind the official Brain seam.

These are not organiser API types. They keep controller/tool/evidence modules aligned while
the inherited harness continues to own iteration, platform calls, and results.json.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class FailureCategory(str, Enum):
    CONFIGURATION = "configuration"
    AUTHENTICATION = "authentication"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    MALFORMED_RESPONSE = "malformed_response"
    TOOL_FAILURE = "tool_failure"
    RESOURCE_LIMIT = "resource_limit"
    RATE_LIMITED = "rate_limited"
    UNKNOWN = "unknown"


class SubmissionStatus(str, Enum):
    CORRECT = "correct"
    INCORRECT = "incorrect"
    ALREADY_SOLVED = "already_solved"
    RATE_LIMITED = "ratelimited"
    ERROR = "error"
    UNCERTAIN = "uncertain"


@dataclass(frozen=True)
class ChallengeScope:
    challenge_id: int
    category: str
    name: str
    material_ref: str
    attempt_id: str
    instance_generation: str | None = None


@dataclass(frozen=True)
class Budget:
    steps_remaining: int
    submissions_remaining: int
    deadline_monotonic: float | None = None


@dataclass(frozen=True)
class ToolResult:
    action_id: str
    observation_ref: str
    provenance_refs: tuple[str, ...]
    excerpt: str
    duration_seconds: float
    cost_units: float = 0.0
    exit_code: int | None = None
    error: FailureCategory | None = None


@dataclass(frozen=True)
class NextAction:
    kind: str
    arguments: dict[str, Any]
    reason: str


@dataclass(frozen=True)
class Candidate:
    value: str = field(repr=False)
    evidence_refs: tuple[str, ...] = ()
    confidence: float = 0.0


@dataclass(frozen=True)
class SubmissionResult:
    intent_id: str
    status: SubmissionStatus
    definitive: bool
    error: FailureCategory | None = None

    def __post_init__(self) -> None:
        definitive_statuses = {
            SubmissionStatus.CORRECT,
            SubmissionStatus.INCORRECT,
            SubmissionStatus.ALREADY_SOLVED,
        }
        if self.definitive != (self.status in definitive_statuses):
            raise ValueError("definitive must match the submission status")
