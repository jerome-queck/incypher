import json
import os
import sqlite3
import sys
import tempfile
import unittest
from types import ModuleType
from unittest.mock import patch

import arena_main
import brain


class _FakeManagedShell:
    instances = []
    response = "[shell status=ok exit=0 elapsed=0.001s truncated=false]\nfresh evidence"

    def __init__(self, scope_ref, deadline_monotonic, **kwargs):
        self.scope_ref = scope_ref
        self.commands = []
        self.events = []
        self.jobs = {}
        self.closed = False
        self.__class__.instances.append(self)

    def __call__(self, command):
        self.commands.append(command)
        self.events.append(("run", command))
        return self.response

    def start(self, command):
        handle = "job-%d" % (len(self.jobs) + 1)
        self.commands.append(command)
        self.events.append(("start", command))
        self.jobs[handle] = command
        return handle

    def poll(self, handle, wait_seconds=0):
        self.events.append(("poll", handle, wait_seconds))
        self.jobs.pop(handle, None)
        return self.response

    def cancel(self, handle):
        self.events.append(("cancel", handle))
        self.jobs.pop(handle, None)
        return "[shell status=cancelled exit=-9 elapsed=0.001s truncated=false]"

    def close(self):
        self.closed = True


class _ScriptedBrain(brain.Brain):
    def __init__(self, replies, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._replies = iter(replies)

    def _chat(self, messages):
        return next(self._replies)


class CoordinatorRecoveryTests(unittest.TestCase):
    def setUp(self):
        _FakeManagedShell.instances = []
        _FakeManagedShell.response = (
            "[shell status=ok exit=0 elapsed=0.001s truncated=false]\nfresh evidence"
        )

    @staticmethod
    def _harness(challenges, solve_challenge, module_name):
        official = ModuleType("main")
        solver = ModuleType(module_name)
        solver.build_prompt = lambda ch, cdir, filenames, conn: "base prompt"
        solver.run_bash = lambda cmd: "original shell"
        solve_challenge.__module__ = module_name
        official.solve_challenge = solve_challenge
        official.is_practice = lambda ch: False

        class Client:
            def __init__(self, base, token):
                self.base = base
                self.token = token

            def list_challenges(self):
                return [dict(challenge, solved=False) for challenge in challenges]

            def challenge(self, cid):
                return dict(next(
                    challenge for challenge in challenges
                    if challenge["id"] == int(cid)
                ))

        official.CTFdClient = Client

        def inherited_main():
            client = official.CTFdClient("base", "token")
            targets = client.list_challenges()
            targets.sort(key=lambda challenge: challenge["id"])
            for brief in targets:
                challenge = client.challenge(brief["id"])
                official.solve_challenge(client, challenge, 3)
            return 0

        official.main = inherited_main
        return official, solver

    def test_restart_projects_memory_and_dedupes_exact_command(self):
        challenge = {
            "id": 7,
            "name": "durable",
            "category": "misc",
            "type": "standard",
            "value": 100,
            "files": [],
        }
        prompts = []
        outputs = []

        def solve_challenge(client, ch, max_steps):
            prompts.append(solver.build_prompt(ch, material_directory, [], None))
            outputs.append(solver.run_bash("inspect material"))
            return {
                "solved": False,
                "steps": 1,
                "model_calls": 1,
                "tool_calls": 1,
            }

        official, solver = self._harness(
            [challenge], solve_challenge, "restart_recovery_solver"
        )
        with tempfile.TemporaryDirectory() as directory:
            material_directory = directory
            environment = {
                "RUNTIME_STATE_PATH": os.path.join(directory, "runtime.sqlite3"),
            }
            with (
                patch.dict(sys.modules, {
                    "main": official,
                    "restart_recovery_solver": solver,
                }),
                patch.dict(os.environ, environment, clear=True),
                patch("arena_main.ManagedShell", _FakeManagedShell),
            ):
                self.assertEqual(arena_main.main(), 0)
                self.assertEqual(arena_main.main(), 0)

        self.assertNotIn("Restart-safe prior evidence", prompts[0])
        self.assertIn("Restart-safe prior evidence", prompts[1])
        self.assertIn("bounded shell outcome: ok", prompts[1])
        self.assertTrue(outputs[0].startswith("[shell status=ok"))
        self.assertEqual(
            outputs[1],
            "duplicate:no new evidence; choose a materially different command",
        )
        self.assertEqual(len(_FakeManagedShell.instances), 1)
        self.assertEqual(_FakeManagedShell.instances[0].commands, ["inspect material"])
        self.assertTrue(_FakeManagedShell.instances[0].closed)

    def test_crash_checkpoint_reorders_the_next_inherited_lifecycle(self):
        challenges = [
            {
                "id": 1,
                "name": "high",
                "category": "web",
                "type": "standard",
                "value": 500,
                "files": [],
            },
            {
                "id": 2,
                "name": "low",
                "category": "crypto",
                "type": "standard",
                "value": 100,
                "files": [],
            },
        ]
        events = []
        crash = True

        def solve_challenge(client, ch, max_steps):
            nonlocal crash
            events.append(("solve", ch["id"]))
            if crash:
                crash = False
                solver.build_prompt(ch, material_directory, [], None)
                solver.run_bash("evidence before crash")
                raise RuntimeError("synthetic crash")
            return {
                "solved": False,
                "steps": 0,
                "model_calls": 0,
                "tool_calls": 0,
            }

        official, solver = self._harness(
            challenges, solve_challenge, "crash_recovery_solver"
        )
        returned = []

        def inherited_one_target():
            client = official.CTFdClient("base", "token")
            targets = client.list_challenges()
            targets.sort(key=lambda challenge: challenge["id"])
            challenge = client.challenge(targets[0]["id"])
            returned.append(official.solve_challenge(client, challenge, 3))
            return 0

        official.main = inherited_one_target
        original_challenge = official.CTFdClient.challenge

        def observed_challenge(self, cid):
            events.append(("detail", int(cid)))
            return original_challenge(self, cid)

        official.CTFdClient.challenge = observed_challenge

        with tempfile.TemporaryDirectory() as directory:
            material_directory = directory
            state_path = os.path.join(directory, "runtime.sqlite3")
            with (
                patch.dict(sys.modules, {
                    "main": official,
                    "crash_recovery_solver": solver,
                }),
                patch.dict(os.environ, {
                    "RUNTIME_STATE_PATH": state_path,
                }, clear=True),
                patch("agent_ext.runtime_state.time.time", return_value=100.0),
                patch("arena_main.ManagedShell", _FakeManagedShell),
            ):
                self.assertEqual(arena_main.main(), 0)
                self.assertEqual(events, [("detail", 1), ("solve", 1)])
                self.assertEqual(returned[0]["error"], "RuntimeError: attempt crashed")
                connection = sqlite3.connect(state_path)
                try:
                    progress = connection.execute(
                        "SELECT progress FROM challenge_state WHERE challenge_id = 1"
                    ).fetchone()[0]
                finally:
                    connection.close()
                self.assertGreater(progress, 0)

                events.clear()
                self.assertEqual(arena_main.main(), 0)

        self.assertEqual(events, [("detail", 2), ("solve", 2)])

    def test_async_shell_flows_through_harness_and_persists_evidence(self):
        challenge = {
            "id": 11, "name": "async", "category": "misc", "type": "standard",
            "value": 100, "files": [],
        }

        def solve_challenge(client, ch, max_steps):
            prompt = solver.build_prompt(ch, material_directory, [], None)
            replies = [
                {"content": "", "tool_calls": [{"id": "start", "function": {
                    "name": "start_bash",
                    "arguments": json.dumps({"command": "long inspection"}),
                }}]},
                {"content": "", "tool_calls": [{"id": "poll", "function": {
                    "name": "poll_bash",
                    "arguments": json.dumps({"handle": "job-1", "wait_seconds": 1}),
                }}]},
                {"content": "done"},
            ]
            return _ScriptedBrain(
                replies, solver.run_bash, lambda flag: {"status": "incorrect"},
                max_steps=max_steps, verbose=False,
            ).solve(prompt)

        official, solver = self._harness(
            [challenge], solve_challenge, "async_recovery_solver"
        )
        with tempfile.TemporaryDirectory() as directory:
            material_directory = directory
            state_path = os.path.join(directory, "runtime.sqlite3")
            with (
                patch.dict(sys.modules, {
                    "main": official, "async_recovery_solver": solver,
                }),
                patch.dict(os.environ, {"RUNTIME_STATE_PATH": state_path}, clear=True),
                patch("arena_main.ManagedShell", _FakeManagedShell),
            ):
                self.assertEqual(arena_main.main(), 0)
            connection = sqlite3.connect(state_path)
            try:
                observation_count = connection.execute(
                    "SELECT COUNT(*) FROM observations WHERE challenge_id = 11"
                ).fetchone()[0]
                progress = connection.execute(
                    "SELECT progress FROM challenge_state WHERE challenge_id = 11"
                ).fetchone()[0]
            finally:
                connection.close()

        self.assertEqual(observation_count, 1)
        self.assertGreaterEqual(progress, 4)
        self.assertEqual(_FakeManagedShell.instances[0].events, [
            ("start", "long inspection"), ("poll", "job-1", 1),
        ])
        self.assertTrue(_FakeManagedShell.instances[0].closed)

    def test_quiet_stall_is_bounded_and_durable_through_harness(self):
        challenge = {
            "id": 12, "name": "quiet", "category": "misc", "type": "standard",
            "value": 100, "files": [],
        }
        results = []

        def solve_challenge(client, ch, max_steps):
            prompt = solver.build_prompt(ch, material_directory, [], None)
            replies = [{"content": "", "tool_calls": [{"id": str(index), "function": {
                "name": "run_bash",
                "arguments": json.dumps({"command": "same inspection"}),
            }}]} for index in range(4)]
            result = _ScriptedBrain(
                replies, solver.run_bash, lambda flag: {"status": "incorrect"},
                max_steps=6, verbose=False,
            ).solve(prompt)
            results.append(result)
            return result

        official, solver = self._harness(
            [challenge], solve_challenge, "quiet_recovery_solver"
        )
        with tempfile.TemporaryDirectory() as directory:
            material_directory = directory
            state_path = os.path.join(directory, "runtime.sqlite3")
            with (
                patch.dict(sys.modules, {
                    "main": official, "quiet_recovery_solver": solver,
                }),
                patch.dict(os.environ, {"RUNTIME_STATE_PATH": state_path}, clear=True),
                patch("arena_main.ManagedShell", _FakeManagedShell),
            ):
                self.assertEqual(arena_main.main(), 0)
            connection = sqlite3.connect(state_path)
            try:
                outcome, progress = connection.execute(
                    "SELECT last_outcome, progress FROM challenge_state "
                    "WHERE challenge_id = 12"
                ).fetchone()
            finally:
                connection.close()

        self.assertEqual(results[0]["error"], "quiet stall: no new tool evidence")
        self.assertEqual(_FakeManagedShell.instances[0].commands, ["same inspection"])
        self.assertEqual(outcome, "unsolved")
        self.assertGreaterEqual(progress, 5)

    def test_shell_timeout_is_durably_classified(self):
        challenge = {
            "id": 9, "name": "timeout", "category": "misc", "type": "standard",
            "value": 100, "files": [],
        }

        def solve_challenge(client, ch, max_steps):
            solver.build_prompt(ch, material_directory, [], None)
            solver.run_bash("slow inspection")
            return {"solved": False, "steps": 1, "model_calls": 1, "tool_calls": 1}

        official, solver = self._harness(
            [challenge], solve_challenge, "timeout_recovery_solver"
        )
        _FakeManagedShell.response = (
            "[shell status=timeout exit=-9 elapsed=45.000s truncated=false]"
        )
        with tempfile.TemporaryDirectory() as directory:
            material_directory = directory
            state_path = os.path.join(directory, "runtime.sqlite3")
            with (
                patch.dict(sys.modules, {
                    "main": official, "timeout_recovery_solver": solver,
                }),
                patch.dict(os.environ, {"RUNTIME_STATE_PATH": state_path}, clear=True),
                patch("arena_main.ManagedShell", _FakeManagedShell),
            ):
                self.assertEqual(arena_main.main(), 0)
            connection = sqlite3.connect(state_path)
            try:
                outcome = connection.execute(
                    "SELECT last_outcome FROM challenge_state WHERE challenge_id = 9"
                ).fetchone()[0]
            finally:
                connection.close()
        self.assertEqual(outcome, "timeout")


if __name__ == "__main__":
    unittest.main()
