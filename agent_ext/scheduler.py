"""Pure challenge ranking using private policy records, not organizer API types."""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum


def bounded_ref(value: str, name: str) -> None:
    """Validate a sanitized identifier, never a prompt, credential, or endpoint."""
    if not isinstance(value, str) or not value or len(value) > 160:
        raise ValueError(
            f"{name} must be a nonempty reference of at most 160 characters"
        )
    if not value.isascii() or any(
        ord(char) <= 32 or ord(char) == 127 for char in value
    ):
        raise ValueError(
            f"{name} must be a printable ASCII reference without whitespace"
        )


def finite_number(value: float, name: str, *, positive: bool = False) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    try:
        valid = math.isfinite(value) and (value > 0 if positive else value >= 0)
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(
            f"{name} must be finite and {'positive' if positive else 'nonnegative'}"
        )


def positive_int(value: int, name: str) -> None:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True)
class Scope:
    challenge_id: str
    material_id: str
    instance_id: str | None = None

    def __post_init__(self) -> None:
        bounded_ref(self.challenge_id, "challenge_id")
        bounded_ref(self.material_id, "material_id")
        if self.instance_id is not None:
            bounded_ref(self.instance_id, "instance_id")

    @property
    def sort_key(self) -> tuple[str, str, str]:
        return self.challenge_id, self.material_id, self.instance_id or ""


@dataclass(frozen=True)
class Challenge:
    """Qualified metadata supplied by Jerome, with optional measured cost fields."""

    scope: Scope
    authority_ref: str
    category: str | None = None
    points: float | None = None
    setup_seconds: float | None = None
    remaining_seconds: float | None = None
    requires: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not isinstance(self.scope, Scope):
            raise ValueError("scope must be a Scope")
        bounded_ref(self.authority_ref, "authority_ref")
        if self.category is not None:
            bounded_ref(self.category, "category")
        for name in ("points", "setup_seconds", "remaining_seconds"):
            value = getattr(self, name)
            if value is not None:
                finite_number(value, name, positive=name == "remaining_seconds")
        if not isinstance(self.requires, frozenset):
            raise ValueError(
                "requires must be an immutable set of subsystem references"
            )
        for subsystem in self.requires:
            bounded_ref(subsystem, "subsystem")


class SelectionPolicy(str, Enum):
    COVERAGE = "coverage"
    PROGRESS = "progress"
    BENEFIT_COST = "benefit_cost"


@dataclass(frozen=True)
class SchedulingRecord:
    challenge: Challenge
    eligible: bool = True
    attempts: int = 0
    bypasses: int = 0
    progress_revision: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.challenge, Challenge) or type(self.eligible) is not bool:
            raise ValueError("invalid scheduling record")
        for name in ("attempts", "bypasses", "progress_revision"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 0:
                raise ValueError(f"{name} must be a nonnegative integer")


def select_challenge(
    records: Iterable[SchedulingRecord],
    *,
    policy: SelectionPolicy = SelectionPolicy.PROGRESS,
    max_bypasses: int = 3,
) -> SchedulingRecord | None:
    """Rank eligible work without mutating it or fabricating missing estimates.

    Coverage comes before ordinary continuation; bypass aging prevents a stream of
    newly arriving tasks from starving an existing eligible task. The controller
    counts only selections at which a task actually was eligible.
    """
    if not isinstance(policy, SelectionPolicy):
        raise ValueError("unknown selection policy")
    positive_int(max_bypasses, "max_bypasses")
    eligible = [record for record in records if record.eligible]
    if len({record.challenge.scope for record in eligible}) != len(eligible):
        raise ValueError("duplicate eligible scope")

    def key(record: SchedulingRecord) -> tuple:
        aged = record.bypasses >= max_bypasses
        prefix = (not aged, -record.bypasses if aged else 0, record.attempts != 0)
        challenge = record.challenge
        if policy is SelectionPolicy.COVERAGE:
            return (*prefix, challenge.scope.sort_key)
        cost = (
            challenge.setup_seconds is None,
            challenge.setup_seconds if challenge.setup_seconds is not None else 0,
        )
        progress = -record.progress_revision
        if policy is SelectionPolicy.BENEFIT_COST:
            known = all(
                value is not None
                for value in (
                    challenge.points,
                    challenge.setup_seconds,
                    challenge.remaining_seconds,
                )
            )
            # This is points/cost, NOT an inferred or model-reported solve probability.
            benefit = (
                challenge.points
                / (challenge.setup_seconds + challenge.remaining_seconds)
                if known
                else 0
            )
            return (
                *prefix,
                not known,
                -benefit,
                progress,
                cost,
                challenge.scope.sort_key,
            )
        return (*prefix, progress, cost, challenge.scope.sort_key)

    return min(eligible, key=key, default=None)
