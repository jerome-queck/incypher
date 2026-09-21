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
    def test_public_scoreboard_events_become_crowd_priority_at_refresh(self):
        body = b'''<script id="ev" type="application/json">{
            "recent": [
                {"team": "a", "challenge": "easy", "value": 100},
                {"team": "b", "challenge": "easy", "value": 100},
                {"team": "c", "challenge": "hard", "value": 500}
            ]}</script>'''
        self.assertEqual(
            arena_main._scoreboard_crowd_counts(body),
            {"easy": 2, "hard": 1},
        )

        now = [0.0]
        crowd_calls = []

        class Delegate:
            def list_challenges(self):
                return [
                    {"id": 1, "name": "hard", "points": 100},
                    {"id": 2, "name": "easy", "points": 100},
                ]

        def crowd_source():
            crowd_calls.append(1)
            return arena_main._scoreboard_crowd_counts(body)

        cache = arena_main._CatalogueCache(
            clock=lambda: now[0], crowd_source=crowd_source
        )
        self.assertEqual(cache.list_challenges(Delegate())[1]["solves"], 2)
        now[0] = 299.0
        cache.list_challenges(Delegate())
        self.assertEqual(len(crowd_calls), 1)
        now[0] = 300.0
        cache.list_challenges(Delegate())
        self.assertEqual(len(crowd_calls), 2)

    def test_catalogue_cache_refreshes_at_five_minutes_and_returns_copies(self):
        now = [0.0]

        class Delegate:
            calls = 0

            def list_challenges(self):
                self.calls += 1
                return [{"id": 1, "points": 100, "solves": self.calls}]

        delegate = Delegate()
        cache = arena_main._CatalogueCache(clock=lambda: now[0])
        first = cache.list_challenges(delegate)
        first[0]["solves"] = 999
        now[0] = 299.999
        self.assertEqual(cache.list_challenges(delegate)[0]["solves"], 1)
        self.assertEqual(delegate.calls, 1)
        now[0] = 300.0
        self.assertEqual(cache.list_challenges(delegate)[0]["solves"], 2)
        self.assertEqual(delegate.calls, 2)

    def test_catalogue_refresh_reconciles_before_ranking(self):
        refreshed = []

        class Delegate:
            def list_challenges(self):
                return [{"id": 1, "points": 100, "solved": False}]

        cache = arena_main._CatalogueCache(
            clock=lambda: 0,
            on_refresh=lambda briefs: refreshed.append([dict(item) for item in briefs]),
        )
        cache.list_challenges(Delegate())
        self.assertEqual(refreshed, [[{"id": 1, "points": 100, "solved": False}]])

    def test_refreshed_crowd_counts_reorder_the_next_ranked_catalogue(self):
        now = [0.0]

        class Delegate:
            calls = 0

            def list_challenges(self):
                self.calls += 1
                if self.calls == 1:
                    return [
                        {"id": 1, "points": 100, "solves": 0},
                        {"id": 2, "points": 100, "solves": 10},
                    ]
                return [
                    {"id": 1, "points": 100, "solves": 20},
                    {"id": 2, "points": 100, "solves": 10},
                ]

            def challenge(self, challenge_id):
                return {"id": challenge_id}

        with tempfile.TemporaryDirectory() as directory:
            state = arena_main.RuntimeState(os.path.join(directory, "state.sqlite3"))
            delegate = Delegate()
            cache = arena_main._CatalogueCache(clock=lambda: now[0])
            client = arena_main._RankedClient(delegate, state, cache)
            self.assertEqual([int(item["id"]) for item in client.list_challenges()], [2, 1])
            now[0] = 299.0
            self.assertEqual([int(item["id"]) for item in client.list_challenges()], [2, 1])
            now[0] = 300.0
            self.assertEqual([int(item["id"]) for item in client.list_challenges()], [1, 2])
            self.assertEqual(delegate.calls, 2)

    def test_temporary_refresh_failure_keeps_cache_and_backs_off_full_cadence(self):
        now = [0.0]

        class Delegate:
            calls = 0

            def list_challenges(self):
                self.calls += 1
                if self.calls == 2:
                    raise OSError("temporary catalogue read failure")
                return [{"id": 1, "points": 100, "solves": self.calls}]

        delegate = Delegate()
        cache = arena_main._CatalogueCache(clock=lambda: now[0])
        self.assertEqual(cache.list_challenges(delegate)[0]["solves"], 1)
        now[0] = 300.0
        self.assertEqual(cache.list_challenges(delegate)[0]["solves"], 1)
        now[0] = 599.999
        self.assertEqual(cache.list_challenges(delegate)[0]["solves"], 1)
        self.assertEqual(delegate.calls, 2)
        now[0] = 600.0
        self.assertEqual(cache.list_challenges(delegate)[0]["solves"], 3)
        self.assertEqual(delegate.calls, 3)

    def test_initial_or_malformed_catalogue_failure_still_fails_closed(self):
        class TemporaryFailure:
            def list_challenges(self):
                raise OSError("no trusted snapshot")

        class Malformed:
            def list_challenges(self):
                return {"not": "a list"}

        with self.assertRaises(OSError):
            arena_main._CatalogueCache(clock=lambda: 0).list_challenges(
                TemporaryFailure()
            )
        with self.assertRaisesRegex(RuntimeError, "catalogue changed"):
            arena_main._CatalogueCache(clock=lambda: 0).list_challenges(Malformed())

    def test_coordinator_runs_one_slice_before_safe_queue_reschedule(self):
        coordinator = arena_main._OuterCoordinator()
        self.assertEqual(coordinator.admit(4), (4, None))
        self.assertEqual(coordinator.admit(4), (None, "queue reschedule"))
        coordinator.begin_pass()
        self.assertEqual(coordinator.admit(4), (4, None))

    def test_attempt_failures_do_not_stop_the_outer_queue(self):
        for error in (
            "model request failed",
            "malformed model message",
            "submission unavailable: uncertain",
        ):
            with self.subTest(error=error):
                coordinator = arena_main._OuterCoordinator()
                self.assertEqual(coordinator.admit(4), (4, None))
                coordinator.note_result(solved=False)
                self.assertTrue(coordinator.should_continue())

        coordinator = arena_main._OuterCoordinator()
        self.assertEqual(coordinator.admit(4), (4, None))
        coordinator.note_result(solved=False, budget_exhausted=True)
        self.assertFalse(coordinator.should_continue())

        coordinator = arena_main._OuterCoordinator()
        self.assertEqual(coordinator.admit(4), (4, None))
        coordinator.note_result(solved=False, unresolved_dispatch=True)
        self.assertFalse(coordinator.should_continue())
        self.assertEqual(coordinator.stop_reason, "unresolved model dispatch")

    def test_per_slice_budget_exhaustion_is_requeueable_not_provider_uncertainty(self):
        shell = SimpleNamespace(failure_outcome=None)
        for error in ("tool call budget exhausted", "submission budget exhausted"):
            with self.subTest(error=error):
                self.assertIs(
                    arena_main._failure_class({"error": error}, shell),
                    arena_main.AttemptOutcome.UNSOLVED,
                )
        self.assertIs(
            arena_main._failure_class(
                {"error": "GatewayError: model budget exhausted"}, shell
            ),
            arena_main.AttemptOutcome.PROVIDER,
        )

    def test_tool_budget_exhaustion_cycles_into_a_later_solve_pass(self):
        challenge = {
            "id": 1,
            "name": "synthetic",
            "category": "misc",
            "type": "standard",
            "points": 100,
            "files": [],
        }
        official = ModuleType("main")
        official.is_practice = lambda ch: False
        solver = ModuleType("budget_cycle_solver")
        solver.build_prompt = lambda ch, cdir, filenames, conn: "synthetic"
        solver.run_bash = lambda cmd: "unused"
        attempts = []

        def solve_challenge(client, ch, max_steps):
            attempts.append(int(ch["id"]))
            if len(attempts) == 1:
                return {
                    "solved": False,
                    "steps": 1,
                    "model_calls": 1,
                    "tool_calls": 1,
                    "error": "tool call budget exhausted",
                }
            return {
                "solved": True,
                "steps": 1,
                "model_calls": 1,
                "tool_calls": 0,
            }

        solve_challenge.__module__ = "budget_cycle_solver"
        official.solve_challenge = solve_challenge

        class Client:
            def __init__(self, base, token):
                self.base, self.token = base, token

            def list_challenges(self):
                return [dict(challenge, solved=False)]

            def challenge(self, cid):
                return dict(challenge)

        official.CTFdClient = Client
        main_calls = []

        def inherited_main():
            main_calls.append(1)
            client = official.CTFdClient("base", "token")
            targets = [item for item in client.list_challenges() if not item.get("solved")]
            targets.sort(key=lambda item: item["id"])
            for brief in targets:
                official.solve_challenge(client, client.challenge(brief["id"]), 3)
            return 0

        official.main = inherited_main
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            sys.modules,
            {"main": official, "budget_cycle_solver": solver},
        ), patch.dict(os.environ, {
            "RUNTIME_STATE_PATH": os.path.join(directory, "state.sqlite3"),
        }, clear=True), patch("arena_main.time.sleep"):
            self.assertEqual(arena_main.main(), 0)

        self.assertEqual(attempts, [1, 1])
        self.assertEqual(len(main_calls), 2)

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
        self.assertEqual(attempted, [1])

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
        }, clear=True), patch.object(
            arena_main._OuterCoordinator, "should_continue", return_value=False
        ):
            self.assertEqual(arena_main.main(), 0)

        self.assertEqual(detail_ids, [3, 2, 1])
        self.assertEqual(delegated_ids, [3])
        self.assertEqual(len(results), 3)
        self.assertIn("queue reschedule", results[1]["error"])
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

            def get(self, url, timeout, stream, headers=None):
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

    def test_all_solved_catalogue_runs_official_main_once(self):
        challenges = [{
            "id": 1, "name": "solved", "category": "misc", "type": "standard",
            "points": 100, "solved": True, "files": [],
        }]
        official = ModuleType("main")
        solver = ModuleType("terminal_catalogue_solver")
        solver.build_prompt = lambda ch, cdir, filenames, conn: "synthetic"
        solver.run_bash = lambda cmd: "unused"
        solves = []

        def solve_challenge(client, ch, max_steps):
            solves.append(ch["id"])
            return {"solved": True, "model_calls": 1, "tool_calls": 0}

        solve_challenge.__module__ = "terminal_catalogue_solver"
        official.solve_challenge = solve_challenge
        official.is_practice = lambda ch: False

        class Client:
            def __init__(self, base, token):
                pass

            def list_challenges(self):
                return challenges

            def challenge(self, cid):
                return dict(challenges[0])

        official.CTFdClient = Client
        main_calls = []

        def inherited_main():
            main_calls.append(1)
            client = official.CTFdClient("base", "token")
            for brief in client.list_challenges():
                official.solve_challenge(client, client.challenge(brief["id"]), 4)
            return 0

        official.main = inherited_main
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            sys.modules, {
                "main": official,
                "terminal_catalogue_solver": solver,
            }
        ), patch.dict(os.environ, {
            "RUNTIME_STATE_PATH": os.path.join(directory, "state.sqlite3"),
        }, clear=True):
            self.assertEqual(arena_main.main(), 0)

        self.assertEqual(main_calls, [1])
        self.assertEqual(solves, [])

    def test_empty_catalogue_is_retried_until_work_arrives(self):
        challenge = {
            "id": 1, "name": "arrived", "category": "misc", "type": "standard",
            "points": 100, "solved": False, "files": [],
        }
        official = ModuleType("main")
        solver = ModuleType("recovering_catalogue_solver")
        solver.build_prompt = lambda ch, cdir, filenames, conn: "synthetic"
        solver.run_bash = lambda cmd: "unused"
        attempts = []

        def solve_challenge(client, ch, max_steps):
            attempts.append(ch["id"])
            return {"solved": True, "model_calls": 1, "tool_calls": 0}

        solve_challenge.__module__ = "recovering_catalogue_solver"
        official.solve_challenge = solve_challenge
        official.is_practice = lambda ch: False

        class Client:
            def __init__(self, base, token):
                pass

            def list_challenges(self):
                return [challenge]

            def challenge(self, cid):
                return dict(challenge)

        official.CTFdClient = Client
        main_calls = []

        def inherited_main():
            main_calls.append(1)
            if len(main_calls) == 1:
                return 0
            client = official.CTFdClient("base", "token")
            for brief in client.list_challenges():
                official.solve_challenge(client, client.challenge(brief["id"]), 4)
            return 0

        official.main = inherited_main
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            sys.modules, {
                "main": official,
                "recovering_catalogue_solver": solver,
            }
        ), patch.dict(os.environ, {
            "RUNTIME_STATE_PATH": os.path.join(directory, "state.sqlite3"),
        }, clear=True), patch("arena_main.time.sleep"):
            self.assertEqual(arena_main.main(), 0)

        self.assertEqual(main_calls, [1, 1])
        self.assertEqual(attempts, [1])
