import unittest
from dataclasses import replace

from agent_ext.memory import EvidenceCompleteness, EvidenceReference, EvidenceScope
from agent_ext.verification import (
    CandidateRecord,
    CandidateSource,
    DuplicateDisposition,
    VerificationKind,
    VerificationStatus,
    qualify_candidate,
    record_local_verification,
)


class VerificationTests(unittest.TestCase):
    def setUp(self):
        self.scope = EvidenceScope(
            "run-1", "solve", 4, "material-a", "attempt-a", "instance-a"
        )
        self.reference = EvidenceReference(
            "evidence:one", EvidenceCompleteness.COMPLETE, "tool:fixture"
        )
        self.candidate = CandidateRecord(
            "private-candidate-1",
            b"FLAG{synthetic}",
            self.scope,
            CandidateSource.TOOL,
            ("evidence:one",),
        )
        self.validator = lambda value: value.startswith(b"FLAG{") and value.endswith(b"}")

    def test_r06_qualification_is_explicit_and_does_not_claim_verification(self):
        result = qualify_candidate(
            self.candidate,
            self.scope,
            format_validator=self.validator,
            evidence={"evidence:one": self.reference},
        )
        self.assertTrue(result.eligible)
        with self.assertRaises(TypeError):
            bool(result)
        local = record_local_verification(
            kind=None, check_id=None, outcome=None, evidence=None
        )
        self.assertEqual(local.status, VerificationStatus.NOT_PERFORMED)
        self.assertFalse(local.passed)

    def test_r06_flag_shape_model_agreement_and_zero_exit_are_not_proof(self):
        for kind in (
            VerificationKind.MODEL_AGREEMENT,
            VerificationKind.FORMAT_ONLY,
            VerificationKind.ZERO_EXIT_ONLY,
        ):
            with self.subTest(kind=kind):
                local = record_local_verification(
                    kind=kind,
                    check_id="check-1",
                    input_refs=("input:one",),
                    outcome=True,
                    evidence=self.reference,
                )
                self.assertEqual(local.status, VerificationStatus.UNAVAILABLE)
                self.assertFalse(local.passed)

    def test_r06_meaningful_complete_check_can_pass_or_fail(self):
        for outcome, expected in (
            (True, VerificationStatus.PASSED),
            (False, VerificationStatus.FAILED),
        ):
            with self.subTest(outcome=outcome):
                local = record_local_verification(
                    kind=VerificationKind.DETERMINISTIC_POSTCONDITION,
                    check_id="check-meaningful",
                    input_refs=("input:one",),
                    outcome=outcome,
                    evidence=self.reference,
                )
                self.assertEqual(local.status, expected)

    def test_r12_incomplete_or_mismatched_evidence_blocks_proof_claim(self):
        partial = replace(
            self.reference, completeness=EvidenceCompleteness.PARTIAL
        )
        result = qualify_candidate(
            self.candidate,
            self.scope,
            format_validator=self.validator,
            evidence={"evidence:one": partial},
        )
        self.assertFalse(result.eligible)
        self.assertIn("evidence_not_complete", result.reasons)
        local = record_local_verification(
            kind=VerificationKind.INDEPENDENT_REDERIVATION,
            check_id="check-2",
            input_refs=("input:one",),
            outcome=True,
            evidence=partial,
        )
        self.assertEqual(local.status, VerificationStatus.UNAVAILABLE)

        changed = replace(self.scope, material_ref="material-b")
        mismatch = qualify_candidate(
            self.candidate,
            changed,
            format_validator=self.validator,
            evidence={"evidence:one": self.reference},
        )
        self.assertIn("scope_or_instance_mismatch", mismatch.reasons)

    def test_duplicate_state_blocks_qualification_without_changing_candidate_bytes(self):
        for disposition in DuplicateDisposition:
            if disposition is DuplicateDisposition.NEW:
                continue
            with self.subTest(disposition=disposition):
                result = qualify_candidate(
                    self.candidate,
                    self.scope,
                    format_validator=self.validator,
                    evidence={"evidence:one": self.reference},
                    duplicate=disposition,
                )
                self.assertFalse(result.eligible)
                self.assertIn("duplicate_" + disposition.value, result.reasons)


if __name__ == "__main__":
    unittest.main()
