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
from agent_ext.runtime_context import (
    Finding,
    FindingDisposition,
    FindingKind,
    current_attempt,
)


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
                return [
                    dict(challenge, solved=challenge.get("solved", False))
                    for challenge in challenges
                ]

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
                official.solve_challenge(client, challenge, 6)
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
                patch.object(
                    arena_main._OuterCoordinator, "should_continue", return_value=False
                ),
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

    def test_prior_slices_reach_brain_scope_after_outer_restart(self):
        challenge = {
            "id": 78, "name": "hard synthetic", "category": "crypto",
            "type": "standard", "value": 200, "files": [],
        }
        observed = []

        def solve_challenge(client, ch, max_steps):
            observed.append(current_attempt(required=True).prior_attempts)
            return {"solved": False, "steps": 0, "model_calls": 0, "tool_calls": 0}

        official, solver = self._harness(
            [challenge], solve_challenge, "multimodel_attempt_scope_solver"
        )
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.dict(sys.modules, {
                "main": official,
                "multimodel_attempt_scope_solver": solver,
                }),
                patch.dict(os.environ, {
                    "RUNTIME_STATE_PATH": os.path.join(directory, "runtime.sqlite3"),
                }, clear=True),
                patch.object(arena_main._OuterCoordinator, "should_continue", return_value=False),
            ):
                for _ in range(3):
                    self.assertEqual(arena_main.main(), 0)
        self.assertEqual(observed, [0, 1, 2])

    def test_crash_checkpoint_reorders_the_next_same_run_pass(self):
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
                "solved": True,
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
                patch("arena_main.time.sleep"),
            ):
                self.assertEqual(arena_main.main(), 0)
                self.assertEqual(events, [
                    ("detail", 2), ("solve", 2),
                    ("detail", 1), ("solve", 1),
                ])
                self.assertEqual(returned[0]["error"], "RuntimeError: attempt crashed")
                connection = sqlite3.connect(state_path)
                try:
                    progress = connection.execute(
                        "SELECT progress FROM challenge_state WHERE challenge_id = 2"
                    ).fetchone()[0]
                finally:
                    connection.close()
                self.assertGreater(progress, 0)
                self.assertEqual(len(returned), 2)

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
                patch.object(
                    arena_main._OuterCoordinator, "should_continue", return_value=False
                ),
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
                patch.object(
                    arena_main._OuterCoordinator, "should_continue", return_value=False
                ),
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
                patch.object(
                    arena_main._OuterCoordinator, "should_continue", return_value=False
                ),
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

    def test_outer_passes_are_serial_cooled_until_challenge_solves(self):
        challenge = {
            "id": 21, "name": "multipass", "category": "misc",
            "type": "standard", "value": 100, "files": [],
        }
        findings = (
            "The decoder first reverses each fixed width block.",
            "The checksum covers decoded bytes before padding.",
            "The comparison accepts a lowercase hexadecimal digest.",
            "The final branch requires an even decoded length.",
        )
        calls = []
        active = 0

        def solve_challenge(client, ch, max_steps):
            nonlocal active
            self.assertEqual(active, 0)
            active += 1
            try:
                calls.append((ch["id"], max_steps))
                disposition = solver.run_bash.checkpoint_finding(
                    Finding(FindingKind.OBSERVED, findings[len(calls) - 1])
                )
                self.assertIs(disposition, FindingDisposition.SAVED)
                return {
                    "solved": len(calls) == 4, "steps": 1,
                    "model_calls": 1, "tool_calls": 0,
                }
            finally:
                active -= 1

        official, solver = self._harness(
            [challenge], solve_challenge, "multipass_solver"
        )
        sleeps = []
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.dict(sys.modules, {"main": official, "multipass_solver": solver}),
                patch.dict(os.environ, {
                    "RUNTIME_STATE_PATH": os.path.join(directory, "runtime.sqlite3"),
                }, clear=True),
                patch("arena_main.time.sleep", side_effect=sleeps.append),
            ):
                self.assertEqual(arena_main.main(), 0)

        self.assertEqual(calls, [(21, 6)] * 4)
        self.assertEqual(sleeps, [2.0, 2.0, 2.0])

    def test_duplicate_finding_does_not_remove_unsolved_work_from_queue(self):
        challenge = {
            "id": 22, "name": "duplicate", "category": "misc",
            "type": "standard", "value": 100, "files": [],
        }
        dispositions = []

        def solve_challenge(client, ch, max_steps):
            dispositions.append(solver.run_bash.checkpoint_finding(Finding(
                FindingKind.OBSERVED,
                "The parser strips a trailing newline before decoding.",
            )))
            return {
                "solved": len(dispositions) == 4, "steps": 1,
                "model_calls": 1, "tool_calls": 0,
            }

        official, solver = self._harness(
            [challenge], solve_challenge, "duplicate_finding_solver"
        )
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.dict(sys.modules, {
                    "main": official, "duplicate_finding_solver": solver,
                }),
                patch.dict(os.environ, {
                    "RUNTIME_STATE_PATH": os.path.join(directory, "runtime.sqlite3"),
                }, clear=True),
                patch("arena_main.time.sleep"),
            ):
                self.assertEqual(arena_main.main(), 0)

        self.assertEqual(
            dispositions,
            [
                FindingDisposition.SAVED,
                FindingDisposition.DUPLICATE,
                FindingDisposition.DUPLICATE,
                FindingDisposition.DUPLICATE,
            ],
        )

    def test_saved_finding_enables_second_pass_solve(self):
        challenge = {
            "id": 23, "name": "finding-retry", "category": "misc",
            "type": "standard", "value": 100, "files": [],
        }
        attempts = []

        def solve_challenge(client, ch, max_steps):
            attempts.append(ch["id"])
            if len(attempts) == 1:
                self.assertIs(
                    solver.run_bash.checkpoint_finding(Finding(
                        FindingKind.HYPOTHESIS,
                        "The checksum likely covers bytes before final padding.",
                    )),
                    FindingDisposition.SAVED,
                )
                return {
                    "solved": False, "steps": 1,
                    "model_calls": 1, "tool_calls": 1,
                }
            return {
                "solved": True, "steps": 1,
                "model_calls": 1, "tool_calls": 0,
            }

        official, solver = self._harness(
            [challenge], solve_challenge, "finding_retry_solver"
        )
        sleeps = []
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.dict(sys.modules, {
                    "main": official, "finding_retry_solver": solver,
                }),
                patch.dict(os.environ, {
                    "RUNTIME_STATE_PATH": os.path.join(directory, "runtime.sqlite3"),
                }, clear=True),
                patch("arena_main.time.sleep", side_effect=sleeps.append),
            ):
                self.assertEqual(arena_main.main(), 0)

        self.assertEqual(attempts, [23, 23])
        self.assertEqual(sleeps, [2.0])

    def test_no_arbitrary_run_call_cap_shrinks_configured_slice_budget(self):
        challenges = [
            {"id": challenge_id, "name": f"budget-{challenge_id}",
             "category": "misc", "type": "standard", "value": 100, "files": []}
            for challenge_id in (31, 32, 33)
        ]
        allocated = []

        def solve_challenge(client, ch, max_steps):
            allocated.append(max_steps)
            self.assertIs(
                solver.run_bash.checkpoint_finding(Finding(
                    FindingKind.OBSERVED,
                    "The verifier normalizes case before comparing the digest."
                    if ch["id"] == 31 else
                    "The verifier checks length before normalizing the digest."
                )),
                FindingDisposition.SAVED,
            )
            return {
                "solved": True, "steps": max_steps,
                "model_calls": max_steps, "tool_calls": 0,
            }

        official, solver = self._harness(
            challenges, solve_challenge, "model_budget_solver"
        )

        def high_step_main():
            client = official.CTFdClient("base", "token")
            for brief in client.list_challenges():
                official.solve_challenge(client, client.challenge(brief["id"]), 100)
            return 0

        official.main = high_step_main
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.dict(sys.modules, {"main": official, "model_budget_solver": solver}),
                patch.dict(os.environ, {
                    "RUNTIME_STATE_PATH": os.path.join(directory, "runtime.sqlite3"),
                }, clear=True),
            ):
                self.assertEqual(arena_main.main(), 0)

        self.assertEqual(allocated, [100, 100, 100])

    def test_provider_failure_requeues_and_later_work_continues(self):
        challenges = [
            {"id": challenge_id, "name": f"provider-{challenge_id}",
             "category": "misc", "type": "standard", "value": 100, "files": []}
            for challenge_id in (41, 42)
        ]
        attempted = []

        def solve_challenge(client, ch, max_steps):
            attempted.append(ch["id"])
            if len(attempted) > 1:
                return {
                    "solved": True, "steps": 1,
                    "model_calls": 1, "tool_calls": 0,
                }
            return {
                "solved": False, "steps": 1, "model_calls": 1, "tool_calls": 0,
                "error": "GatewayError: model request failed",
            }

        official, solver = self._harness(
            challenges, solve_challenge, "provider_stop_solver"
        )
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.dict(sys.modules, {"main": official, "provider_stop_solver": solver}),
                patch.dict(os.environ, {
                    "RUNTIME_STATE_PATH": os.path.join(directory, "runtime.sqlite3"),
                }, clear=True),
            ):
                self.assertEqual(arena_main.main(), 0)

        self.assertEqual(attempted, [41, 42, 41])

    def test_malformed_provider_message_requeues_and_later_work_continues(self):
        challenges = [
            {"id": challenge_id, "name": f"malformed-{challenge_id}",
             "category": "misc", "type": "standard", "value": 100, "files": []}
            for challenge_id in (43, 44)
        ]
        attempted = []

        def solve_challenge(client, ch, max_steps):
            attempted.append(ch["id"])
            if len(attempted) > 1:
                return {
                    "solved": True, "steps": 1,
                    "model_calls": 1, "tool_calls": 0,
                }
            solver.run_bash("inspect malformed response")
            return {
                "solved": False, "steps": 1, "model_calls": 1, "tool_calls": 1,
                "error": "malformed model message",
            }

        official, solver = self._harness(
            challenges, solve_challenge, "malformed_provider_stop_solver"
        )
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.dict(sys.modules, {
                    "main": official, "malformed_provider_stop_solver": solver,
                }),
                patch.dict(os.environ, {
                    "RUNTIME_STATE_PATH": os.path.join(directory, "runtime.sqlite3"),
                }, clear=True),
                patch("arena_main.ManagedShell", _FakeManagedShell),
            ):
                self.assertEqual(arena_main.main(), 0)

        self.assertEqual(attempted, [43, 44, 43])

    def test_crashed_slices_do_not_shrink_later_configured_slice_budget(self):
        challenges = [{
            "id": 71, "name": "crash-retry", "category": "misc",
            "type": "standard", "value": 100, "files": [],
        }]
        attempted = []

        def solve_challenge(client, ch, max_steps):
            attempted.append((ch["id"], max_steps))
            for _ in range(max_steps):
                solver.run_bash.record_model_progress()
            if len(attempted) < 3:
                raise RuntimeError("synthetic crash after accepted turns")
            return {
                "solved": True, "steps": 1, "model_calls": 1, "tool_calls": 0,
            }

        official, solver = self._harness(
            challenges, solve_challenge, "crash_budget_solver"
        )

        def high_step_main():
            client = official.CTFdClient("base", "token")
            for brief in client.list_challenges():
                official.solve_challenge(client, client.challenge(brief["id"]), 100)
            return 0

        official.main = high_step_main
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.dict(sys.modules, {"main": official, "crash_budget_solver": solver}),
                patch.dict(os.environ, {
                    "RUNTIME_STATE_PATH": os.path.join(directory, "runtime.sqlite3"),
                }, clear=True),
                patch("arena_main.time.sleep"),
            ):
                self.assertEqual(arena_main.main(), 0)

        self.assertEqual(attempted, [(71, 100), (71, 100), (71, 100)])

    def test_submission_uncertainty_requeues_and_later_work_continues(self):
        challenges = [
            {"id": challenge_id, "name": f"submission-{challenge_id}",
             "category": "misc", "type": "standard", "value": 100, "files": []}
            for challenge_id in (51, 52)
        ]
        attempted = []

        def solve_challenge(client, ch, max_steps):
            attempted.append(ch["id"])
            if len(attempted) > 1:
                return {
                    "solved": True, "steps": 1,
                    "model_calls": 1, "tool_calls": 0,
                }
            return {
                "solved": False, "steps": 1, "model_calls": 1, "tool_calls": 0,
                "error": "submission unavailable: uncertain",
                "verdict": {"status": "uncertain"},
            }

        official, solver = self._harness(
            challenges, solve_challenge, "submission_stop_solver"
        )
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.dict(sys.modules, {
                    "main": official, "submission_stop_solver": solver,
                }),
                patch.dict(os.environ, {
                    "RUNTIME_STATE_PATH": os.path.join(directory, "runtime.sqlite3"),
                }, clear=True),
            ):
                self.assertEqual(arena_main.main(), 0)

        self.assertEqual(attempted, [51, 52, 51])

    def test_raised_submission_callback_blocks_replay_while_later_work_continues(self):
        challenges = [
            {"id": challenge_id, "name": f"raised-submission-{challenge_id}",
             "category": "misc", "type": "standard", "value": 100, "files": []}
            for challenge_id in (53, 54)
        ]
        attempted = []

        def solve_challenge(client, ch, max_steps):
            attempted.append(ch["id"])
            if len(attempted) > 1:
                return {
                    "solved": True, "steps": 1,
                    "model_calls": 1, "tool_calls": 0,
                }
            prompt = solver.build_prompt(ch, material_directory, [], None)
            replies = [{"content": "", "tool_calls": [{"id": "submit", "function": {
                "name": "submit_flag",
                "arguments": json.dumps({"flag": "INCYPHER{synthetic}"}),
            }}]}]

            def uncertain_submission(_flag):
                raise RuntimeError("transport failed after possible delivery")

            return _ScriptedBrain(
                replies, solver.run_bash, uncertain_submission,
                max_steps=max_steps, verbose=False,
            ).solve(prompt)

        official, solver = self._harness(
            challenges, solve_challenge, "raised_submission_stop_solver"
        )
        with tempfile.TemporaryDirectory() as directory:
            material_directory = directory
            with (
                patch.dict(sys.modules, {
                    "main": official, "raised_submission_stop_solver": solver,
                }),
                patch.dict(os.environ, {
                    "RUNTIME_STATE_PATH": os.path.join(directory, "runtime.sqlite3"),
                }, clear=True),
                patch.object(
                    arena_main._OuterCoordinator,
                    "should_continue",
                    side_effect=(True, False),
                ),
                patch("arena_main.time.sleep"),
            ):
                self.assertEqual(arena_main.main(), 0)

        self.assertEqual(attempted, [53, 54])

    def test_deadline_is_hard_but_slice_count_does_not_abandon_unsolved_work(self):
        self.assertEqual(arena_main._MAX_RUN_SECONDS, 86_400)
        with patch("arena_main.time.monotonic", side_effect=[0.0, 86_400.0]):
            deadline = arena_main._OuterCoordinator()
            self.assertEqual(deadline.admit(4), (None, "run deadline"))

        slices = arena_main._OuterCoordinator()
        for _ in range(1_000):
            slices.begin_pass()
            self.assertEqual(slices.admit(1), (1, None))

    def test_attempt_deadline_is_capped_by_outer_run(self):
        challenge = {
            "id": 62, "name": "deadline", "category": "misc",
            "type": "standard", "value": 100, "files": [],
        }
        observed = []

        def solve_challenge(client, ch, max_steps):
            observed.append(current_attempt(required=True).deadline_monotonic)
            return {
                "solved": True, "steps": 1, "model_calls": 1, "tool_calls": 0,
            }

        official, solver = self._harness(
            [challenge], solve_challenge, "outer_deadline_solver"
        )
        started = arena_main.time.monotonic()
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.dict(sys.modules, {
                    "main": official, "outer_deadline_solver": solver,
                }),
                patch.dict(os.environ, {
                    "RUNTIME_STATE_PATH": os.path.join(directory, "runtime.sqlite3"),
                    "ATTEMPT_TIMEOUT_SECONDS": "480",
                }, clear=True),
                patch("arena_main._MAX_RUN_SECONDS", 30),
            ):
                self.assertEqual(arena_main.main(), 0)

        self.assertEqual(len(observed), 1)
        self.assertGreater(observed[0], started)
        self.assertLessEqual(observed[0], started + 30.1)

    def test_wrapper_scopes_spend_pacing_and_restores_environment(self):
        challenge = {
            "id": 64, "name": "pacing", "category": "misc",
            "type": "standard", "value": 100, "files": [],
        }

        for label, initial, validation, observed_value in (
            ("arena default", {}, False, "adaptive"),
            ("explicit practice setting", {"MODEL_SPEND_PACING": "fixed_high"},
             False, "fixed_high"),
            ("validation default", {}, True, None),
        ):
            with self.subTest(label=label):
                observed = []

                def solve_challenge(client, ch, max_steps):
                    observed.append(os.environ.get("MODEL_SPEND_PACING"))
                    return {
                        "solved": True, "steps": 1,
                        "model_calls": 1, "tool_calls": 0,
                    }

                module_name = "scoped_pacing_" + label.replace(" ", "_")
                official, solver = self._harness(
                    [challenge], solve_challenge, module_name
                )
                with tempfile.TemporaryDirectory() as directory:
                    environment = {
                        "RUNTIME_STATE_PATH": os.path.join(
                            directory, "runtime.sqlite3"
                        ),
                        **initial,
                    }
                    with (
                        patch.dict(sys.modules, {"main": official, module_name: solver}),
                        patch.dict(os.environ, environment, clear=True),
                        patch("arena_main.os.path.isfile", return_value=validation),
                    ):
                        self.assertEqual(arena_main.main(), 0)
                        self.assertEqual(
                            os.environ.get("MODEL_SPEND_PACING"),
                            initial.get("MODEL_SPEND_PACING"),
                        )
                self.assertEqual(observed, [observed_value])

    def test_wrapper_restores_spend_pacing_after_error(self):
        challenge = {
            "id": 65, "name": "pacing-error", "category": "misc",
            "type": "standard", "value": 100, "files": [],
        }

        def solve_challenge(client, ch, max_steps):
            self.fail("wrapper failure should precede solver dispatch")

        official, solver = self._harness(
            [challenge], solve_challenge, "scoped_pacing_error_solver"
        )

        def failing_main():
            self.assertEqual(os.environ.get("MODEL_SPEND_PACING"), "adaptive")
            raise RuntimeError("synthetic wrapper failure")

        official.main = failing_main
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.dict(sys.modules, {
                    "main": official, "scoped_pacing_error_solver": solver,
                }),
                patch.dict(os.environ, {
                    "RUNTIME_STATE_PATH": os.path.join(directory, "runtime.sqlite3"),
                }, clear=True),
            ):
                with self.assertRaisesRegex(RuntimeError, "synthetic wrapper failure"):
                    arena_main.main()
                self.assertNotIn("MODEL_SPEND_PACING", os.environ)

    def test_wrapper_rejects_out_of_range_inherited_step_budget(self):
        challenge = {
            "id": 63, "name": "invalid budget", "category": "misc",
            "type": "standard", "value": 100, "files": [],
        }

        for invalid in (0, 151):
            with self.subTest(invalid=invalid):
                def solve_challenge(client, ch, max_steps):
                    self.fail("invalid inherited budget reached the solver")

                module_name = f"invalid_budget_solver_{invalid}"
                official, solver = self._harness(
                    [challenge], solve_challenge, module_name
                )

                def invalid_main():
                    client = official.CTFdClient("base", "token")
                    official.solve_challenge(client, client.challenge(63), invalid)

                official.main = invalid_main
                with tempfile.TemporaryDirectory() as directory:
                    with (
                        patch.dict(sys.modules, {"main": official, module_name: solver}),
                        patch.dict(os.environ, {
                            "RUNTIME_STATE_PATH": os.path.join(
                                directory, "runtime.sqlite3"
                            ),
                        }, clear=True),
                    ):
                        with self.assertRaisesRegex(RuntimeError, "arguments changed"):
                            arena_main.main()

    def test_dynamic_lifecycles_cleanup_before_each_outer_pass(self):
        challenge = {
            "id": 61, "name": "dynamic", "category": "misc",
            "type": "dynamic_iac", "value": 100, "files": [],
        }
        calls = []
        lifecycle = {"live": False, "cleanups": 0}

        def solve_challenge(client, ch, max_steps):
            calls.append(ch["id"])
            solver.build_prompt(ch, material_directory, [], "synthetic connection")
            solver.run_bash(f"inspect generation {len(calls)}")
            return {
                "solved": len(calls) == 4, "steps": 1,
                "model_calls": 1, "tool_calls": 1,
            }

        official, solver = self._harness(
            [challenge], solve_challenge, "dynamic_serial_solver"
        )

        def lifecycle_main():
            self.assertFalse(lifecycle["live"])
            lifecycle["live"] = True
            client = official.CTFdClient("base", "token")
            try:
                brief = client.list_challenges()[0]
                official.solve_challenge(client, client.challenge(brief["id"]), 6)
            finally:
                lifecycle["live"] = False
                lifecycle["cleanups"] += 1
            return 0

        official.main = lifecycle_main
        with tempfile.TemporaryDirectory() as directory:
            material_directory = directory
            with (
                patch.dict(sys.modules, {
                    "main": official, "dynamic_serial_solver": solver,
                }),
                patch.dict(os.environ, {
                    "RUNTIME_STATE_PATH": os.path.join(directory, "runtime.sqlite3"),
                }, clear=True),
                patch("arena_main.ManagedShell", _FakeManagedShell),
                patch("arena_main.time.sleep"),
            ):
                self.assertEqual(arena_main.main(), 0)

        self.assertEqual(calls, [61] * 4)
        self.assertEqual(lifecycle, {"live": False, "cleanups": 4})
        self.assertTrue(all(shell.closed for shell in _FakeManagedShell.instances))

    def test_later_official_pass_synthesizes_locally_solved_result(self):
        challenges = [
            {"id": challenge_id, "name": f"mixed-{challenge_id}",
             "category": "misc", "type": "standard", "value": 100, "files": []}
            for challenge_id in (71, 72)
        ]
        attempts = []
        pass_results = []

        def solve_challenge(client, ch, max_steps):
            attempts.append(ch["id"])
            if ch["id"] == 71:
                challenges[0]["solved"] = True
                return {
                    "solved": True, "steps": 1,
                    "model_calls": 1, "tool_calls": 0,
                }
            if attempts.count(72) == 1:
                solver.run_bash("inspect mixed challenge")
            solved = attempts.count(72) == 2
            if solved:
                challenges[1]["solved"] = True
            return {
                "solved": solved, "steps": 1,
                "model_calls": 1, "tool_calls": 0,
            }

        official, solver = self._harness(
            challenges, solve_challenge, "mixed_result_solver"
        )

        def captured_main():
            client = official.CTFdClient("base", "token")
            results = []
            for brief in client.list_challenges():
                results.append(official.solve_challenge(
                    client, client.challenge(brief["id"]), 6
                ))
            pass_results.append(results)
            return 0

        official.main = captured_main
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.dict(sys.modules, {"main": official, "mixed_result_solver": solver}),
                patch.dict(os.environ, {
                    "RUNTIME_STATE_PATH": os.path.join(directory, "runtime.sqlite3"),
                }, clear=True),
                patch("arena_main.ManagedShell", _FakeManagedShell),
                patch("arena_main.time.sleep"),
            ):
                self.assertEqual(arena_main.main(), 0)

        self.assertEqual(attempts, [71, 72, 72])
        self.assertEqual(len(pass_results), 3)
        synthesized = next(item for item in pass_results[1] if item.get("id") == 71)
        self.assertTrue(synthesized["solved"])
        self.assertEqual(synthesized["model_calls"], 0)


if __name__ == "__main__":
    unittest.main()
