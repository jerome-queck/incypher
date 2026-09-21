import json
import os
import sys
import tempfile
import unittest
from types import ModuleType
from types import SimpleNamespace
from unittest.mock import patch

import arena_main
import brain
from agent_ext.runtime_context import current_attempt


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

    def test_fake_harness_reaches_gateway_tool_and_original_submit_once(self):
        candidate = "INCYPHER" + "{integrated-synthetic}"

        class Response:
            def __init__(self, payload):
                self.body = json.dumps(payload).encode()
                self.headers = {"Content-Length": str(len(self.body))}

            def raise_for_status(self):
                return None

            def iter_content(self, chunk_size):
                yield self.body

            def close(self):
                return None

        class Session:
            def __init__(self):
                self.headers = {}
                self.responses = iter([
                    {"model": "openai/integration-model", "choices": [{"message": {
                        "role": "assistant", "content": "", "tool_calls": [{
                            "id": "inspect", "function": {
                                "name": "run_bash",
                                "arguments": json.dumps({"command": "inspect"}),
                            },
                        }],
                    }}], "usage": {"cost": "0.0001"}},
                    {"model": "openai/integration-model", "choices": [{"message": {
                        "role": "assistant", "content": "", "tool_calls": [{
                            "id": "submit", "function": {
                                "name": "submit_flag",
                                "arguments": json.dumps({"flag": candidate}),
                            },
                        }],
                    }}], "usage": {"cost": "0.0001"}},
                ])

            def get(self, url, timeout, stream):
                return Response({"data": [{
                    "id": "openai/integration-model",
                    "canonical_slug": "openai/integration-model",
                    "supported_parameters": [
                        "tools", "tool_choice", "max_completion_tokens", "reasoning",
                    ],
                    "pricing": {"prompt": "0.000001", "completion": "0.000002"},
                }]})

            def post(self, endpoint, headers, data, timeout, stream):
                return Response(next(self.responses))

        challenge = {
            "id": 1, "name": "synthetic", "category": "web", "type": "static",
            "points": 100, "files": [],
        }
        official = ModuleType("main")
        official.is_practice = lambda ch: False
        solver = ModuleType("integrated_solver")
        tool_calls, submissions, results = [], [], []

        def build_prompt(ch, cdir, filenames, conn):
            return "Inspect the synthetic fixture."

        solver.build_prompt = build_prompt

        def solve_challenge(client, ch, max_steps):
            prompt = solver.build_prompt(ch, material_directory, ["fixture.bin"], None)
            agent = brain.Brain(
                lambda command: tool_calls.append(command) or candidate,
                lambda flag: submissions.append(flag) or {"status": "correct"},
                max_steps=max_steps,
                verbose=False,
            )
            results.append(agent.solve(prompt))
            return results[-1]

        solve_challenge.__module__ = "integrated_solver"
        official.solve_challenge = solve_challenge
        official.main = lambda: official.solve_challenge(None, challenge, 3) and 0

        with tempfile.TemporaryDirectory() as directory:
            material_directory = directory
            with open(os.path.join(directory, "fixture.bin"), "wb") as stream:
                stream.write(b"synthetic")
            with (
                patch.dict(sys.modules, {"main": official, "integrated_solver": solver}),
                patch("brain.requests.Session", return_value=Session()),
                patch.dict(os.environ, {
                    "LLM_BASE_URL": "https://openrouter.ai/api/v1",
                    "LLM_MODEL": "openai/integration-model",
                    "LLM_API_KEY": "secret",
                    "MODEL_BUDGET_PATH": os.path.join(directory, "budget.sqlite3"),
                    "MODEL_BUDGET_USD": "1",
                }, clear=True),
            ):
                self.assertEqual(arena_main.main(), 0)

        self.assertTrue(results[0]["solved"])
        self.assertEqual(tool_calls, ["inspect"])
        self.assertEqual(submissions, [candidate])
        self.assertIsNone(current_attempt())

    def test_cancellation_restores_context_and_official_hooks(self):
        challenge = {
            "id": 1, "name": "synthetic", "category": "web", "type": "static",
            "points": 100, "files": [],
        }
        official = ModuleType("main")
        official.is_practice = lambda ch: False
        solver = ModuleType("cancelling_solver")
        original_builder = lambda ch, cdir, filenames, conn: "synthetic"
        solver.build_prompt = original_builder

        def solve_challenge(client, ch, max_steps):
            self.assertIsNotNone(current_attempt())
            raise KeyboardInterrupt("synthetic cancellation")

        solve_challenge.__module__ = "cancelling_solver"
        official.solve_challenge = solve_challenge
        official.main = lambda: official.solve_challenge(None, challenge, 3)
        with patch.dict(sys.modules, {"main": official, "cancelling_solver": solver}):
            with self.assertRaises(KeyboardInterrupt):
                arena_main.main()
        self.assertIsNone(current_attempt())
        self.assertIs(official.solve_challenge, solve_challenge)
        self.assertIs(solver.build_prompt, original_builder)
