import unittest
import json
from pathlib import Path

from agent_ext.challenge_methods import METHODS, method_for


class ChallengeMethodsTests(unittest.TestCase):
    def test_packaged_reference_has_all_methods_and_no_candidates(self):
        root = Path(__file__).resolve().parents[1] / "challenge_reference"
        raw = (root / "index.json").read_text()
        self.assertNotIn("INCYPHER{", raw)
        self.assertNotIn("flag{", raw)
        entries = json.loads(raw)
        self.assertEqual(len(entries), 47)
        self.assertEqual({entry["id"] for entry in entries}, set(METHODS))
        self.assertEqual(sum(len(entry["artifacts"]) for entry in entries), 19)

    def test_methods_are_bounded_hypotheses_without_candidate_values(self):
        for challenge_id, method in METHODS.items():
            self.assertEqual(method_for(challenge_id), method)
            self.assertLess(len(method), 700)
            self.assertNotIn("INCYPHER{", method)
            self.assertNotIn("flag{", method)
        self.assertEqual(method_for("105"), "")
        self.assertEqual(method_for(999999), "")
