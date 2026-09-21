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
        official.is_practice = lambda ch: "Practice" in ch["category"]
        solver = ModuleType("synthetic_solver")

        def build_prompt(ch, cdir, filenames, conn):
            return "synthetic"

        solver.build_prompt = build_prompt
        solver.run_bash = lambda cmd: "synthetic"

        def solve_challenge(client, ch, max_steps):
            solver.build_prompt(ch, "/tmp", [], None)
            attempted.append(ch["id"])
            return {"solved": False, "seconds": 0.0, "steps": 0,
                    "model_calls": 0, "tool_calls": 0}

        solve_challenge.__module__ = "synthetic_solver"
        official.solve_challenge = solve_challenge

        class Client:
            def __init__(self, base, token):
                self.base, self.token = base, token

            def list_challenges(self):
                return challenges

            def challenge(self, cid):
                return dict(next(ch for ch in challenges if ch["id"] == cid), files=[])

        official.CTFdClient = Client

        def inherited_main():
            selected = {int(i) for i in os.environ["ONLY_IDS"].split(",")}
            client = official.CTFdClient("base", "token")
            targets = [c for c in client.list_challenges() if not official.is_practice(c)]
            targets = [c for c in targets if c["id"] in selected]
            targets.sort(key=lambda c: c["id"])
            for brief in targets:
                challenge = client.challenge(brief["id"])
                if challenge["id"] in selected and not official.is_practice(challenge):
                    official.solve_challenge(client, challenge, 3)
            return 7

        official.main = inherited_main
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            sys.modules, {"main": official, "synthetic_solver": solver}
        ), patch.dict(os.environ, {
            "ONLY_IDS": "1,2",
            "RUNTIME_STATE_PATH": os.path.join(directory, "state.sqlite3"),
        }, clear=True):
            self.assertEqual(arena_main.main(), 7)
            self.assertEqual(os.environ["ONLY_IDS"], "1,2")
        self.assertEqual(attempted, [1, 2])

    def test_changed_trusted_solver_hook_fails_before_harness_runs(self):
        official = ModuleType("main")
        official.is_practice = lambda ch: False
        official.main = lambda: self.fail("changed harness must not run")
        official.solve_challenge = lambda prompt: None
        with patch.dict(sys.modules, {"main": official}):
            with self.assertRaisesRegex(RuntimeError, "solve-challenge"):
                arena_main.main()

    def test_ranked_ids_preserve_filters_and_solved_briefs_skip_solver(self):
        briefs = [
            {"id": 1, "name": "settled", "category": "web", "type": "standard",
             "points": 100, "value": 100, "solved": True},
            {"id": 2, "name": "high", "category": "pwn", "type": "standard",
             "points": 500, "value": 500, "solved": False},
            {"id": 3, "name": "middle", "category": "misc", "type": "standard",
             "points": 250, "value": 250, "solved": False},
        ]
        delegated_ids, detail_ids, results = [], [], []
        official = ModuleType("main")
        official.is_practice = lambda ch: False
        solver = ModuleType("ranking_solver")
        solver.build_prompt = lambda ch, cdir, filenames, conn: "synthetic"
        solver.run_bash = lambda cmd: "unused"

        def solve_challenge(client, ch, max_steps):
            delegated_ids.append(ch["id"])
            return {"solved": False, "seconds": 0.0, "steps": 0,
                    "model_calls": 0, "tool_calls": 0}

        solve_challenge.__module__ = "ranking_solver"
        official.solve_challenge = solve_challenge

        class Client:
            def __init__(self, base, token):
                self.base, self.token = base, token

            def list_challenges(self):
                return briefs

            def challenge(self, cid):
                self_test.assertIs(type(cid), int)
                detail_ids.append(cid)
                return dict(next(item for item in briefs if item["id"] == cid), files=[])

        self_test = self
        official.CTFdClient = Client

        def inherited_main():
            client = official.CTFdClient("base", "token")
            targets = [item for item in client.list_challenges() if item["id"] in {1, 2, 3}]
            targets.sort(key=lambda item: item["id"])
            for brief in targets:
                results.append(official.solve_challenge(
                    client, client.challenge(brief["id"]), 3
                ))
            return 0

        official.main = inherited_main
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            sys.modules, {"main": official, "ranking_solver": solver}
        ), patch.dict(os.environ, {
            "RUNTIME_STATE_PATH": os.path.join(directory, "state.sqlite3"),
        }, clear=True):
            self.assertEqual(arena_main.main(), 0)

        self.assertEqual(detail_ids, [2, 3, 1])
        self.assertEqual(delegated_ids, [2, 3])
        self.assertEqual(len(results), 3)
        self.assertEqual(results[-1]["model_calls"], 0)
        self.assertTrue(results[-1]["solved"])

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

        def run_bash(cmd):
            tool_calls.append(cmd)
            return candidate

        solver.run_bash = run_bash

        def solve_challenge(client, ch, max_steps):
            prompt = solver.build_prompt(ch, material_directory, ["fixture.bin"], None)
            agent = brain.Brain(
                solver.run_bash,
                lambda flag: submissions.append(flag) or {"status": "correct"},
                max_steps=max_steps,
                verbose=False,
            )
            results.append(agent.solve(prompt))
            return results[-1]

        solve_challenge.__module__ = "integrated_solver"
        official.solve_challenge = solve_challenge

        class Client:
            def __init__(self, base, token):
                self.base, self.token = base, token

            def list_challenges(self):
                return [dict(challenge, solved=False)]

            def challenge(self, cid):
                return dict(challenge)

        official.CTFdClient = Client

        def inherited_main():
            client = official.CTFdClient("base", "token")
            briefs = client.list_challenges()
            briefs.sort(key=lambda c: c["id"])
            for brief in briefs:
                official.solve_challenge(client, client.challenge(brief["id"]), 3)
            return 0

        official.main = inherited_main

        with tempfile.TemporaryDirectory() as directory:
            material_directory = directory
            with open(os.path.join(directory, "fixture.bin"), "wb") as stream:
                stream.write(b"synthetic")
            with (
                patch.dict(sys.modules, {"main": official, "integrated_solver": solver}),
                patch("brain.requests.Session", return_value=Session()),
                patch("arena_main.os.getcwd", return_value="/tmp"),
                patch.dict(os.environ, {
                    "LLM_BASE_URL": "https://openrouter.ai/api/v1",
                    "LLM_MODEL": "openai/integration-model",
                    "LLM_API_KEY": "secret",
                    "MODEL_BUDGET_PATH": os.path.join(directory, "budget.sqlite3"),
                    "MODEL_BUDGET_USD": "1",
                    "RUNTIME_STATE_PATH": os.path.join(directory, "state.sqlite3"),
                }, clear=True),
            ):
                self.assertEqual(arena_main.main(), 0)

        self.assertTrue(results[0]["solved"])
        if sys.platform.startswith("linux"):
            self.assertEqual(tool_calls, [])
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
        original_shell = lambda cmd: "synthetic"
        solver.run_bash = original_shell

        def solve_challenge(client, ch, max_steps):
            self.assertIsNotNone(current_attempt())
            raise KeyboardInterrupt("synthetic cancellation")

        solve_challenge.__module__ = "cancelling_solver"
        official.solve_challenge = solve_challenge
        class Client:
            def __init__(self, base, token):
                self.base, self.token = base, token

            def list_challenges(self):
                return [dict(challenge, solved=False)]

            def challenge(self, cid):
                return dict(challenge)

        official.CTFdClient = Client

        def inherited_main():
            client = official.CTFdClient("base", "token")
            briefs = client.list_challenges()
            briefs.sort(key=lambda c: c["id"])
            return official.solve_challenge(client, client.challenge(briefs[0]["id"]), 3)

        official.main = inherited_main
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            sys.modules, {"main": official, "cancelling_solver": solver}
        ), patch.dict(os.environ, {
            "RUNTIME_STATE_PATH": os.path.join(directory, "state.sqlite3"),
        }, clear=True):
            with self.assertRaises(KeyboardInterrupt):
                arena_main.main()
        self.assertIsNone(current_attempt())
        self.assertIs(official.solve_challenge, solve_challenge)
        self.assertIs(solver.build_prompt, original_builder)
        self.assertIs(solver.run_bash, original_shell)
