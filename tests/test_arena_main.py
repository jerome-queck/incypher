import os
import sys
import unittest
from types import ModuleType
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
            {"id": 1, "name": "one", "category": "Web (Practice)", "type": "standard", "points": 100},
            {"id": 2, "name": "two", "category": "Crypto", "type": "standard", "points": 100},
            {"id": 3, "name": "three", "category": "Pwn (Practice)", "type": "standard", "points": 100},
        ]
        attempted = []
        official = ModuleType("main")
        official.is_practice = lambda c: "Practice" in c["category"]
        solver = ModuleType("synthetic_solver")

        def build_prompt(ch, cdir, filenames, conn):
            return "synthetic"

        solver.build_prompt = build_prompt

        def solve_challenge(client, ch, max_steps):
            solver.build_prompt(ch, "/tmp", [], None)
            attempted.append(ch["id"])
            return {"solved": False}

        solve_challenge.__module__ = "synthetic_solver"
        official.solve_challenge = solve_challenge

        def inherited_main():
            selected = {int(i) for i in os.environ["ONLY_IDS"].split(",")}
            for challenge in challenges:
                if challenge["id"] in selected and not official.is_practice(challenge):
                    official.solve_challenge(None, challenge, 3)
            return 7

        official.main = inherited_main
        with patch.dict(sys.modules, {"main": official, "synthetic_solver": solver}), patch.dict(
            os.environ, {"ONLY_IDS": "1,2"}, clear=True
        ):
            self.assertEqual(arena_main.main(), 7)
            self.assertEqual(os.environ["ONLY_IDS"], "1,2")
        self.assertEqual(attempted, [1, 2])

    def test_changed_trusted_solver_hook_fails_before_harness_runs(self):
        official = ModuleType("main")
        official.is_practice = lambda challenge: False
        official.main = lambda: self.fail("changed harness must not run")
        official.solve_challenge = lambda prompt: None
        with patch.dict(sys.modules, {"main": official}):
            with self.assertRaisesRegex(RuntimeError, "solve-challenge"):
                arena_main.main()
