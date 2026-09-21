"""Candidate qualification and local-verification semantics.

Qualification is an administrative eligibility decision.  It is intentionally
separate from a meaningful local check and from an authoritative platform outcome.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum

from .memory import EvidenceCompleteness, EvidenceReference, EvidenceScope


class CandidateSource(str, Enum):
    TOOL = "tool"
    MODEL = "model"
    HUMAN = "human"
    TRANSFORM = "transform"


class DuplicateDisposition(str, Enum):
    NEW = "new"
    RESERVED = "reserved"
    DISPATCH_POSSIBLE = "dispatch_possible"
    UNKNOWN = "unknown"
    WRONG = "wrong"
    ACCEPTED = "accepted"
    CONFLICT = "conflict"


class VerificationKind(str, Enum):
    DETERMINISTIC_POSTCONDITION = "deterministic_postcondition"
    INDEPENDENT_REDERIVATION = "independent_rederivation"
    MODEL_AGREEMENT = "model_agreement"
    FORMAT_ONLY = "format_only"
    ZERO_EXIT_ONLY = "zero_exit_only"


class VerificationStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_PERFORMED = "not_performed"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class CandidateRecord:
    candidate_id: str
    value: bytes = field(repr=False)
    scope: EvidenceScope = field(repr=False)
    source: CandidateSource = CandidateSource.MODEL
    provenance_refs: tuple[str, ...] = ()
    generation_dependent: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_id, str) or not self.candidate_id:
            raise ValueError("candidate_id must be an opaque private identifier")
        if not isinstance(self.value, bytes) or not self.value or len(self.value) > 4096:
            raise ValueError("candidate bytes must be nonempty and bounded")
        if not isinstance(self.scope, EvidenceScope) or not isinstance(
            self.source, CandidateSource
        ):
            raise ValueError("typed scope and source required")
        if not isinstance(self.provenance_refs, tuple) or not all(
            isinstance(item, str) and item for item in self.provenance_refs
        ):
            raise ValueError("provenance_refs must be nonempty strings")
        if type(self.generation_dependent) is not bool:
            raise ValueError("generation_dependent must be boolean")


@dataclass(frozen=True)
class QualificationResult:
    eligible: bool
    reasons: tuple[str, ...]
    candidate_id: str

    def __bool__(self) -> bool:
        raise TypeError("qualification is explicit; inspect .eligible and .reasons")


@dataclass(frozen=True)
class LocalVerification:
    status: VerificationStatus
    kind: VerificationKind | None
    check_id: str | None
    input_refs: tuple[str, ...]
    evidence_ref: str | None
    reason: str

    @property
    def passed(self) -> bool:
        return self.status is VerificationStatus.PASSED


def qualify_candidate(
    candidate: CandidateRecord,
    current_scope: EvidenceScope,
    *,
    format_validator: Callable[[bytes], bool],
    evidence: Mapping[str, EvidenceReference],
    duplicate: DuplicateDisposition = DuplicateDisposition.NEW,
    require_complete_evidence: bool = True,
) -> QualificationResult:
    """Return every failed gate without performing I/O or claiming verification."""
    if not isinstance(candidate, CandidateRecord) or not isinstance(
        current_scope, EvidenceScope
    ):
        raise ValueError("typed candidate and current scope required")
    if not callable(format_validator):
        raise ValueError("the integration owner must supply the actual format contract")
    if not isinstance(duplicate, DuplicateDisposition):
        raise ValueError("typed duplicate disposition required")

    reasons: list[str] = []
    if not candidate.scope.applies_to(
        current_scope, generation_dependent=candidate.generation_dependent
    ):
        reasons.append("scope_or_instance_mismatch")
    try:
        valid_format = format_validator(candidate.value)
    except Exception:
        valid_format = False
    if type(valid_format) is not bool or not valid_format:
        reasons.append("format_contract_failed")
    if not candidate.provenance_refs:
        reasons.append("missing_provenance")
    else:
        for reference in candidate.provenance_refs:
            record = evidence.get(reference)
            if record is None:
                reasons.append("missing_evidence")
                break
            if require_complete_evidence and record.completeness is not EvidenceCompleteness.COMPLETE:
                reasons.append("evidence_not_complete")
                break
    if duplicate is not DuplicateDisposition.NEW:
        reasons.append(f"duplicate_{duplicate.value}")
    return QualificationResult(not reasons, tuple(dict.fromkeys(reasons)), candidate.candidate_id)


def record_local_verification(
    *,
    kind: VerificationKind | None,
    check_id: str | None,
    input_refs: tuple[str, ...] = (),
    outcome: bool | None,
    evidence: EvidenceReference | None,
    unavailable_reason: str = "no_meaningful_local_verifier",
) -> LocalVerification:
    """Classify a supplied check result without executing a verifier itself."""
    if kind is None or check_id is None or outcome is None:
        return LocalVerification(
            VerificationStatus.NOT_PERFORMED,
            kind,
            check_id,
            input_refs,
            evidence.reference if evidence else None,
            unavailable_reason,
        )
    if not isinstance(kind, VerificationKind):
        raise ValueError("typed verification kind required")
    if not isinstance(check_id, str) or not check_id or len(check_id) > 256:
        raise ValueError("check_id must be bounded and nonempty")
    if type(outcome) is not bool:
        raise ValueError("outcome must be boolean or absent")
    if not isinstance(input_refs, tuple) or not all(
        isinstance(item, str) and item for item in input_refs
    ):
        raise ValueError("input_refs must be nonempty strings")

    meaningful = kind in {
        VerificationKind.DETERMINISTIC_POSTCONDITION,
        VerificationKind.INDEPENDENT_REDERIVATION,
    }
    if not meaningful:
        return LocalVerification(
            VerificationStatus.UNAVAILABLE,
            kind,
            check_id,
            input_refs,
            evidence.reference if evidence else None,
            "assertion_is_not_an_independent_meaningful_check",
        )
    if evidence is None or evidence.completeness is not EvidenceCompleteness.COMPLETE:
        return LocalVerification(
            VerificationStatus.UNAVAILABLE,
            kind,
            check_id,
            input_refs,
            evidence.reference if evidence else None,
            "complete_verification_evidence_unavailable",
        )
    return LocalVerification(
        VerificationStatus.PASSED if outcome else VerificationStatus.FAILED,
        kind,
        check_id,
        input_refs,
        evidence.reference,
        "meaningful_postcondition_passed" if outcome else "meaningful_postcondition_failed",
    )
