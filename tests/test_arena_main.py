import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import arena_main


class ArenaSelectionTests(unittest.TestCase):
    def test_changed_official_hook_fails_before_harness_runs(self):
        official = SimpleNamespace(main=lambda: self.fail("changed harness must be inspected"))
        with patch.dict("sys.modules", {"main": official}):
            with self.assertRaisesRegex(RuntimeError, "hook changed"):
                arena_main.main()

    def test_practice_and_competition_reach_inherited_solver_with_selector_intact(self):
        challenges = [
            {"id": 1, "category": "Web (Practice)"},
            {"id": 2, "category": "Crypto"},
            {"id": 3, "category": "Pwn (Practice)"},
        ]
        attempted = []
        official = SimpleNamespace(is_practice=lambda c: "Practice" in c["category"])

        def inherited_main():
            selected = {int(i) for i in os.environ["ONLY_IDS"].split(",")}
            for challenge in challenges:
                if challenge["id"] in selected and not official.is_practice(challenge):
                    attempted.append(challenge["id"])
            return 7

        official.main = inherited_main
        with patch.dict("sys.modules", {"main": official}), patch.dict(
            os.environ, {"ONLY_IDS": "1,2"}, clear=True
        ):
            self.assertEqual(arena_main.main(), 7)
            self.assertEqual(os.environ["ONLY_IDS"], "1,2")
        self.assertEqual(attempted, [1, 2])
