"""Scoped evidence memory and deterministic model-facing projection.

This module is deliberately pure and dependency free.  It does not call a model,
execute tools, submit candidates, or write the organiser's results file.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Mapping

from .contracts import ChallengeScope


class EvidenceCompleteness(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    INTEGRITY_FAILED = "integrity_failed"


class ExecutionStatus(str, Enum):
    COMPLETED = "completed"
    TIMEOUT = "timeout"
    RESOURCE_LIMIT = "resource_limit"
    TOOL_UNAVAILABLE = "tool_unavailable"
    PERMISSION_DENIED = "permission_denied"
    MALFORMED_OUTPUT = "malformed_output"
    POLICY_BLOCKED = "policy_blocked"
    INTERRUPTED = "interrupted"


class Interpretation(str, Enum):
    SUPPORTS = "supports"
    NEGATIVE = "negative"
    UNRESOLVED = "unresolved"
    UNKNOWN = "unknown"


class ProjectionFailure(ValueError):
    """The mandatory safe decision envelope cannot fit the configured byte bound."""

    def __init__(self, required_bytes: int, maximum_bytes: int):
        super().__init__(
            f"mandatory decision packet requires {required_bytes} UTF-8 bytes; "
            f"limit is {maximum_bytes}"
        )
        self.required_bytes = required_bytes
        self.maximum_bytes = maximum_bytes


@dataclass(frozen=True)
class EvidenceScope:
    run_id: str
    phase: str
    challenge_id: int
    material_ref: str
    attempt_id: str
    instance_generation: str | None = None
    branch_id: str | None = None

    def __post_init__(self) -> None:
        for name in ("run_id", "phase", "material_ref", "attempt_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or len(value) > 4096:
                raise ValueError(f"{name} must be a bounded, known value")
        if type(self.challenge_id) is not int or self.challenge_id <= 0:
            raise ValueError("challenge_id must be a positive integer")
        for name in ("instance_generation", "branch_id"):
            value = getattr(self, name)
            if value is not None and (
                not isinstance(value, str) or not value or len(value) > 4096
            ):
                raise ValueError(f"{name} must be absent or a bounded, known value")

    @classmethod
    def from_shared(
        cls, run_id: str, phase: str, scope: ChallengeScope, *, branch_id: str | None = None
    ) -> "EvidenceScope":
        if not isinstance(scope, ChallengeScope):
            raise ValueError("ChallengeScope required")
        return cls(
            run_id,
            phase,
            scope.challenge_id,
            scope.material_ref,
            scope.attempt_id,
            scope.instance_generation,
            branch_id,
        )

    def applies_to(
        self, current: "EvidenceScope", *, generation_dependent: bool
    ) -> bool:
        if not isinstance(current, EvidenceScope):
            return False
        if (
            self.run_id,
            self.phase,
            self.challenge_id,
            self.material_ref,
        ) != (
            current.run_id,
            current.phase,
            current.challenge_id,
            current.material_ref,
        ):
            return False
        if self.branch_id is not None and self.branch_id != current.branch_id:
            return False
        if generation_dependent:
            return (
                self.instance_generation is not None
                and current.instance_generation is not None
                and self.instance_generation == current.instance_generation
            )
        return True

    def public_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "phase": self.phase,
            "challenge_id": self.challenge_id,
            "material_ref": self.material_ref,
            "instance_generation": self.instance_generation,
            "branch_id": self.branch_id,
        }


@dataclass(frozen=True)
class EvidenceReference:
    reference: str
    completeness: EvidenceCompleteness
    source_binding: str
    retained_range: str | None = None

    def __post_init__(self) -> None:
        for name in ("reference", "source_binding"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or len(value) > 4096:
                raise ValueError(f"{name} must be bounded and nonempty")
        if not isinstance(self.completeness, EvidenceCompleteness):
            raise ValueError("typed evidence completeness required")
        if self.retained_range is not None and (
            not isinstance(self.retained_range, str)
            or not self.retained_range
            or len(self.retained_range) > 1024
        ):
            raise ValueError("retained_range must be absent or bounded")


@dataclass(frozen=True)
class Dependencies:
    artifact_refs: tuple[str, ...] = ()
    procedure: str = ""
    procedure_version: str = ""
    parameters: tuple[tuple[str, str], ...] = ()
    coverage: str = ""
    environment_refs: tuple[str, ...] = ()
    target_session_ref: str | None = None
    host_profile_revision: str | None = None
    profile_sensitive: bool = False

    def __post_init__(self) -> None:
        for collection in (self.artifact_refs, self.environment_refs):
            if not isinstance(collection, tuple) or not all(
                isinstance(item, str) and item and len(item) <= 4096
                for item in collection
            ):
                raise ValueError("dependency references must be bounded tuples")
        if not isinstance(self.parameters, tuple) or not all(
            isinstance(item, tuple)
            and len(item) == 2
            and all(isinstance(part, str) and len(part) <= 4096 for part in item)
            for item in self.parameters
        ):
            raise ValueError("parameters must be a bounded canonical tuple")
        for name in ("procedure", "procedure_version", "coverage"):
            value = getattr(self, name)
            if not isinstance(value, str) or len(value) > 4096:
                raise ValueError(f"{name} must be bounded")
        if type(self.profile_sensitive) is not bool:
            raise ValueError("profile_sensitive must be boolean")

    def reuse_tuple(self) -> tuple[Any, ...]:
        return (
            self.artifact_refs,
            self.procedure,
            self.procedure_version,
            tuple(sorted(self.parameters)),
            self.coverage,
            self.environment_refs,
            self.target_session_ref,
            self.host_profile_revision if self.profile_sensitive else None,
            self.profile_sensitive,
        )


@dataclass(frozen=True)
class Observation:
    observation_id: str
    scope: EvidenceScope
    evidence: EvidenceReference
    summary: str
    execution: ExecutionStatus
    sequence: int
    interpretation: Interpretation = Interpretation.UNRESOLVED
    tested_conditions: str = ""
    generation_dependent: bool = False
    cost_units: float | None = None

    def __post_init__(self) -> None:
        _bounded_id(self.observation_id, "observation_id")
        _bounded_text(self.summary, "summary")
        _bounded_text(self.tested_conditions, "tested_conditions", allow_empty=True)
        if not isinstance(self.scope, EvidenceScope) or not isinstance(
            self.evidence, EvidenceReference
        ):
            raise ValueError("typed scope and evidence required")
        if not isinstance(self.execution, ExecutionStatus) or not isinstance(
            self.interpretation, Interpretation
        ):
            raise ValueError("typed execution and interpretation required")
        if type(self.sequence) is not int or self.sequence < 0:
            raise ValueError("sequence must be a nonnegative integer")
        if self.interpretation in {Interpretation.SUPPORTS, Interpretation.NEGATIVE}:
            if self.execution is not ExecutionStatus.COMPLETED or not self.tested_conditions:
                raise ValueError(
                    "support/negative evidence requires a completed meaningful test and conditions"
                )
        if self.execution is not ExecutionStatus.COMPLETED and self.interpretation not in {
            Interpretation.UNRESOLVED,
            Interpretation.UNKNOWN,
        }:
            raise ValueError("execution limitations cannot settle a hypothesis")
        if self.cost_units is not None and (
            isinstance(self.cost_units, bool) or self.cost_units < 0
        ):
            raise ValueError("cost must be absent or nonnegative")


@dataclass(frozen=True)
class Hypothesis:
    hypothesis_id: str
    scope: EvidenceScope
    claim: str
    supporting_observations: tuple[str, ...] = ()
    opposing_observations: tuple[str, ...] = ()
    sequence: int = 0

    def __post_init__(self) -> None:
        _bounded_id(self.hypothesis_id, "hypothesis_id")
        _bounded_text(self.claim, "claim")
        if not isinstance(self.scope, EvidenceScope):
            raise ValueError("typed scope required")
        if type(self.sequence) is not int or self.sequence < 0:
            raise ValueError("sequence must be nonnegative")


@dataclass(frozen=True)
class Experiment:
    experiment_id: str
    scope: EvidenceScope
    question: str
    dependencies: Dependencies
    expected_outcomes: tuple[str, ...]
    admitted_budget: Mapping[str, float | int]
    deterministic: bool
    generation_dependent: bool
    sequence: int
    execution: ExecutionStatus | None = None
    interpretation: Interpretation = Interpretation.UNRESOLVED
    evidence_refs: tuple[str, ...] = ()
    live_trial_id: str | None = None
    measured_cost: float | None = None
    repeat_reason: str | None = None

    def __post_init__(self) -> None:
        _bounded_id(self.experiment_id, "experiment_id")
        _bounded_text(self.question, "question")
        if not isinstance(self.scope, EvidenceScope) or not isinstance(
            self.dependencies, Dependencies
        ):
            raise ValueError("typed scope and dependencies required")
        if not isinstance(self.expected_outcomes, tuple) or not self.expected_outcomes:
            raise ValueError("expected distinguishing outcomes are required")
        if not isinstance(self.admitted_budget, Mapping):
            raise ValueError("admitted_budget must be a mapping")
        if type(self.deterministic) is not bool or type(self.generation_dependent) is not bool:
            raise ValueError("experiment classifications must be boolean")
        if type(self.sequence) is not int or self.sequence < 0:
            raise ValueError("sequence must be nonnegative")
        if self.execution is not None and not isinstance(self.execution, ExecutionStatus):
            raise ValueError("typed execution required")
        if not isinstance(self.interpretation, Interpretation):
            raise ValueError("typed interpretation required")
        if self.interpretation in {Interpretation.SUPPORTS, Interpretation.NEGATIVE}:
            if self.execution is not ExecutionStatus.COMPLETED:
                raise ValueError("only completed experiments can support or contradict")
            if not self.dependencies.coverage:
                raise ValueError("settled experiment interpretation requires tested coverage")
        if self.execution not in {None, ExecutionStatus.COMPLETED} and self.interpretation not in {
            Interpretation.UNRESOLVED,
            Interpretation.UNKNOWN,
        }:
            raise ValueError("execution limitations leave the hypothesis unresolved")
        if not self.deterministic and not self.live_trial_id:
            raise ValueError("live/stochastic work requires a trial identity")
        if self.measured_cost is not None and (
            isinstance(self.measured_cost, bool) or self.measured_cost < 0
        ):
            raise ValueError("measured cost must be absent or nonnegative")


@dataclass(frozen=True)
class CandidateStatus:
    opaque_ref: str
    qualification: str
    verification: str
    submission: str

    def __post_init__(self) -> None:
        if not re.fullmatch(r"opaque:[A-Za-z0-9_-]{8,64}", self.opaque_ref):
            raise ValueError("candidate projections require a non-derived opaque reference")
        for name in ("qualification", "verification", "submission"):
            _bounded_text(getattr(self, name), name)


@dataclass(frozen=True)
class ReuseDecision:
    reusable: bool
    reason: str
    experiment_id: str | None = None
    evidence_refs: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProjectionResult:
    packet: Mapping[str, Any]
    utf8_bytes: int


_SENSITIVE = re.compile(
    r"(?:INCYPHER\{|https?://|\bBearer\s+|CTF(?:D)?_TOKEN|LLM_API_KEY|"
    r"PRIVATE_ENDPOINT|api[_-]?key\s*[=:])",
    re.IGNORECASE,
)


def _bounded_id(value: str, name: str) -> None:
    if not isinstance(value, str) or not value or len(value) > 256:
        raise ValueError(f"{name} must be bounded and nonempty")


def _bounded_text(value: str, name: str, *, allow_empty: bool = False) -> None:
    if not isinstance(value, str) or (not allow_empty and not value) or len(value) > 8192:
        raise ValueError(f"{name} must be bounded" + ("" if allow_empty else " and nonempty"))


def _safe_text(value: str) -> str:
    if _SENSITIVE.search(value):
        raise ValueError("model/public projection contains private or credential-like text")
    return value


def _encoded(packet: Mapping[str, Any]) -> bytes:
    return json.dumps(
        packet, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


class ScopedMemory:
    """Small linked records with strict applicability and bounded projection."""

    def __init__(self, *, max_records: int = 512):
        if type(max_records) is not int or max_records <= 0:
            raise ValueError("max_records must be positive")
        self.max_records = max_records
        self.observations: list[Observation] = []
        self.hypotheses: list[Hypothesis] = []
        self.experiments: list[Experiment] = []

    def _admit(self) -> None:
        if len(self.observations) + len(self.hypotheses) + len(self.experiments) >= self.max_records:
            raise OverflowError("evidence record capacity reached; checkpoint or increase the bound")

    def add_observation(self, record: Observation) -> None:
        if not isinstance(record, Observation):
            raise ValueError("Observation required")
        self._admit()
        self.observations.append(record)

    def add_hypothesis(self, record: Hypothesis) -> None:
        if not isinstance(record, Hypothesis):
            raise ValueError("Hypothesis required")
        self._admit()
        self.hypotheses.append(record)

    def add_experiment(self, record: Experiment) -> None:
        if not isinstance(record, Experiment):
            raise ValueError("Experiment required")
        self._admit()
        self.experiments.append(record)

    def reusable_experiment(self, proposed: Experiment) -> ReuseDecision:
        if not isinstance(proposed, Experiment):
            raise ValueError("Experiment required")
        if not proposed.deterministic:
            return ReuseDecision(False, "live_or_stochastic_trial_requires_fresh_identity")
        for prior in sorted(self.experiments, key=lambda item: item.sequence, reverse=True):
            if not prior.deterministic or prior.execution is not ExecutionStatus.COMPLETED:
                continue
            if not prior.scope.applies_to(
                proposed.scope, generation_dependent=prior.generation_dependent
            ):
                continue
            if prior.dependencies.reuse_tuple() != proposed.dependencies.reuse_tuple():
                continue
            return ReuseDecision(
                True,
                "equivalent_deterministic_work",
                prior.experiment_id,
                prior.evidence_refs,
            )
        return ReuseDecision(False, "scope_inputs_method_or_coverage_changed")

    def decision_packet(
        self,
        current: EvidenceScope,
        *,
        objective: str,
        request: str,
        restrictions: Iterable[str],
        candidate_statuses: Iterable[CandidateStatus] = (),
        next_experiment: str | None = None,
        maximum_bytes: int = 12_000,
        maximum_records: int = 24,
    ) -> ProjectionResult:
        if not isinstance(current, EvidenceScope):
            raise ValueError("EvidenceScope required")
        if type(maximum_bytes) is not int or maximum_bytes <= 0:
            raise ValueError("maximum_bytes must be positive")
        if type(maximum_records) is not int or maximum_records < 0:
            raise ValueError("maximum_records must be nonnegative")
        safe_restrictions = tuple(_safe_text(item) for item in restrictions)
        statuses = tuple(candidate_statuses)
        if not all(isinstance(item, CandidateStatus) for item in statuses):
            raise ValueError("typed candidate statuses required")
        mandatory = {
            "schema": "decision-packet-v1",
            "scope": current.public_dict(),
            "objective": _safe_text(objective),
            "request": _safe_text(request),
            "trusted_restrictions": safe_restrictions,
            "candidate_statuses": [
                {
                    "opaque_ref": item.opaque_ref,
                    "qualification": _safe_text(item.qualification),
                    "verification": _safe_text(item.verification),
                    "submission": _safe_text(item.submission),
                }
                for item in statuses
            ],
            "observations": [],
            "significant_failed_tests": [],
            "hypotheses": [],
            "next_experiment": (
                None
                if next_experiment is None
                else {
                    "status": "unverified_suggestion",
                    "proposal": _safe_text(next_experiment),
                }
            ),
            "omissions": {
                "observations": 0,
                "significant_failed_tests": 0,
                "hypotheses": 0,
            },
            "uncertainty_preserved": True,
        }

        observations = [
            item
            for item in self.observations
            if item.scope.applies_to(
                current, generation_dependent=item.generation_dependent
            )
        ]
        experiments = [
            item
            for item in self.experiments
            if item.interpretation is Interpretation.NEGATIVE
            and item.scope.applies_to(
                current, generation_dependent=item.generation_dependent
            )
        ]
        hypotheses = [
            item
            for item in self.hypotheses
            if item.scope.applies_to(current, generation_dependent=False)
        ]
        observations.sort(key=lambda item: item.sequence, reverse=True)
        experiments.sort(key=lambda item: item.sequence, reverse=True)
        hypotheses.sort(key=lambda item: item.sequence, reverse=True)

        optional: list[tuple[str, dict[str, Any]]] = []
        for item in observations:
            optional.append(
                (
                    "observations",
                    {
                        "id": item.observation_id,
                        "summary": _safe_text(item.summary),
                        "execution": item.execution.value,
                        "interpretation": item.interpretation.value,
                        "tested_conditions": _safe_text(item.tested_conditions),
                        "evidence": {
                            "reference": item.evidence.reference,
                            "completeness": item.evidence.completeness.value,
                            "source_binding": _safe_text(item.evidence.source_binding),
                            "retained_range": item.evidence.retained_range,
                        },
                        "cost_units": item.cost_units,
                    },
                )
            )
        for item in experiments:
            optional.append(
                (
                    "significant_failed_tests",
                    {
                        "id": item.experiment_id,
                        "question": _safe_text(item.question),
                        "interpretation": "negative_within_tested_conditions",
                        "coverage": _safe_text(item.dependencies.coverage),
                        "execution": item.execution.value if item.execution else None,
                        "evidence_refs": item.evidence_refs,
                    },
                )
            )
        for item in hypotheses:
            optional.append(
                (
                    "hypotheses",
                    {
                        "id": item.hypothesis_id,
                        "status": "unverified_suggestion",
                        "claim": _safe_text(item.claim),
                        "supports": item.supporting_observations,
                        "opposes": item.opposing_observations,
                    },
                )
            )

        counts = {name: 0 for name in mandatory["omissions"]}
        for name, _ in optional:
            counts[name] += 1
        mandatory["omissions"] = dict(counts)
        base_size = len(_encoded(mandatory))
        if base_size > maximum_bytes:
            raise ProjectionFailure(base_size, maximum_bytes)

        included = 0
        for name, value in optional:
            if included >= maximum_records:
                continue
            mandatory[name].append(value)
            mandatory["omissions"][name] -= 1
            if len(_encoded(mandatory)) > maximum_bytes:
                mandatory[name].pop()
                mandatory["omissions"][name] += 1
                continue
            included += 1
        payload = _encoded(mandatory)
        if len(payload) > maximum_bytes:
            raise ProjectionFailure(len(payload), maximum_bytes)
        return ProjectionResult(mandatory, len(payload))
