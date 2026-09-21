import unittest

from agent_ext.contracts import Candidate, SubmissionResult, SubmissionStatus


class ContractTests(unittest.TestCase):
    def test_candidate_value_is_not_in_repr(self):
        candidate = Candidate(value="sensitive", evidence_refs=("observation-1",), confidence=0.9)
        self.assertNotIn("sensitive", repr(candidate))

    def test_definitive_submission_status_is_consistent(self):
        result = SubmissionResult(
            intent_id="intent-1",
            status=SubmissionStatus.CORRECT,
            definitive=True,
        )
        self.assertTrue(result.definitive)

    def test_uncertain_submission_cannot_be_definitive(self):
        with self.assertRaises(ValueError):
            SubmissionResult(
                intent_id="intent-1",
                status=SubmissionStatus.UNCERTAIN,
                definitive=True,
            )


if __name__ == "__main__":
    unittest.main()
