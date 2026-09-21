import copy
import hashlib
import json
import socket
import unittest
from dataclasses import replace
from unittest.mock import patch

from requests import HTTPError, Response

from agent_ext.adapters import ConfigurationError
from agent_ext.contracts import (
    Budget,
    ChallengeScope,
    FailureCategory,
    NextAction,
    SubmissionStatus,
    ToolResult,
)
from agent_ext.controller import (
    Controller,
    ControllerLimits,
    DecisionKind,
    ProgressEvidence,
)
from agent_ext.retry_policy import Failure, FailureKind, Operation
from agent_ext.strategy_bridge import (
    BrainAttempt,
    action_from_decision,
    challenge_from_shared,
    failure_from_tool,
    outcome_from_submission,
    submission_from_verdict,
)
from brain import Brain


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def call(name, arguments, identifier="call-1"):
    return {
        "id": identifier,
        "function": {"name": name, "arguments": json.dumps(arguments)},
    }


class FakeOwners:
    """Synthetic Richard/Aidan callbacks, using the actual merged shared records."""

    def __init__(self, trace, local_scope):
        self.trace = trace
        self.local_scope = local_scope
        self.qualified = True
        self.confirmed = True
        self.error = None
        self.intents = {}
        self.writes = []
        self.fail_checkpoint = False
        self.after_checkpoint = None
        self.fail_release = False

    def observe(self, scope, action, output, seconds):
        if not isinstance(scope, ChallengeScope) or not isinstance(action, NextAction):
            raise AssertionError("owner did not receive merged records")
        self.trace.append("observe")
        result = ToolResult(
            "action-1",
            digest(output),
            (scope.material_ref,),
            output,
            seconds,
            error=self.error,
        )
        evidence = ProgressEvidence(
            self.local_scope, digest(output), confirmed=self.confirmed
        )
        return result, (evidence,)

    def qualify(self, scope, candidate):
        self.trace.append("qualify")
        return self.qualified and bool(candidate.evidence_refs)

    def reserve_intent(self, scope, candidate):
        key = (scope.attempt_id, digest(candidate.value))
        if key in self.intents:
            raise AssertionError("duplicate intent")
        self.trace.append("reserve")
        self.intents[key] = "reserved"
        return "synthetic-intent-1"

    def record_submission(self, scope, result):
        self.trace.append("record:" + result.status.value)
        for key in self.intents:
            self.intents[key] = result.status.value

    def checkpoint(self, scope, state):
        self.trace.append("checkpoint")
        if self.fail_checkpoint:
            self.fail_checkpoint = False
            raise OSError("synthetic checkpoint failure")
        self.writes.append(
            copy.deepcopy({"controller": state, "intents": self.intents})
        )
        if self.after_checkpoint:
            self.after_checkpoint()

    def release(self, scope):
        self.trace.append("release")
        if self.fail_release:
            raise RuntimeError("synthetic cleanup failure")


class StrategyBridgeTests(unittest.TestCase):
    def setUp(self):
        blocker = patch.object(
            socket, "socket", side_effect=AssertionError("unexpected network")
        )
        blocker.start()
        self.addCleanup(blocker.stop)
        self.now = 0
        self.cancelled = False
        self.trace = []
        self.commands = []
        self.submissions = []
        self.scope = ChallengeScope(
            101, "synthetic", "Fixture", "material-1", "parent-1", "gen-1"
        )
        self.task = challenge_from_shared(self.scope, "fixture-authority")
        self.controller = Controller(started_at=0)
        self.controller.update_catalogue([self.task], now=0)
        self.decision = self.controller.next_action(now=0)
        self.owners = FakeOwners(self.trace, self.task.scope)
        self.candidate = "INCYPHER" + "{strategy-bridge-fixture}"
        self.replies = [
            {"tool_calls": [call("run_bash", {"command": "inspect fixture"})]},
            {"tool_calls": [call("submit_flag", {"flag": self.candidate})]},
        ]

    def execute_tool(self, command):
        self.trace.append("tool")
        self.commands.append(command)
        return "synthetic observation"

    def submit(self, value):
        self.assertEqual(
            tuple(self.owners.writes[-1]["intents"].values()), ("reserved",)
        )
        self.trace.append("submit")
        self.submissions.append(value)
        return {"status": "correct"}

    def adapter(self, **kwargs):
        return BrainAttempt(
            self.controller,
            self.decision.attempt,
            self.scope,
            kwargs.pop("budget", Budget(40, 3)),
            self.owners,
            clock=lambda: self.now,
            cancelled=lambda: self.cancelled,
            **kwargs,
        )

    def run_attempt(self, replies=None, adapter=None, submit=None, tool=None):
        with patch.object(
            Brain, "_chat", side_effect=self.replies if replies is None else replies
        ):
            return (adapter or self.adapter()).run(
                "synthetic prompt",
                run_bash=tool or self.execute_tool,
                submit_flag=submit or self.submit,
            )

    def row(self):
        return next(
            item
            for item in self.controller.snapshot()["work"]
            if item["scope"] == self.task.scope
        )

    def test_real_brain_loop_uses_shared_owners_before_single_submission(self):
        result = self.run_attempt()
        self.assertEqual(result["verdict"], {"status": "correct"})
        self.assertTrue(result["solved"])
        self.assertEqual(result["steps"], 2)
        self.assertEqual(self.submissions, [self.candidate])
        self.assertEqual(
            self.trace,
            [
                "tool",
                "observe",
                "qualify",
                "reserve",
                "checkpoint",
                "submit",
                "record:correct",
                "release",
                "checkpoint",
            ],
        )
        self.assertEqual(self.row()["reason"], "accepted")
        self.assertIsNone(self.controller.snapshot()["active_attempt_token"])

    def test_plain_text_candidate_goes_through_same_gate(self):
        self.replies[1] = {"content": self.candidate}
        self.assertTrue(self.run_attempt()["solved"])
        self.assertEqual(len(self.submissions), 1)

    def test_unconfirmed_observation_does_not_bypass_owner_qualification(self):
        self.owners.confirmed = False
        result = self.run_attempt()
        self.assertFalse(result["solved"])
        self.assertEqual(self.submissions, [])
        self.assertEqual(self.row()["reason"], "qualification_rejected")

    def test_explicit_qualification_rejection_never_reserves_or_sends(self):
        self.owners.qualified = False
        self.run_attempt()
        self.assertNotIn("reserve", self.trace)
        self.assertEqual(self.submissions, [])

    def test_unknown_or_uncertain_verdict_never_sends_second_candidate(self):
        for verdict in (
            None,
            [],
            {"status": []},
            {"status": "unexpected"},
            {"status": "ratelimited"},
            {"status": "error"},
            {"status": "uncertain"},
        ):
            with self.subTest(verdict=verdict):
                controller = Controller(started_at=0)
                controller.update_catalogue([self.task], now=0)
                owners = FakeOwners([], self.task.scope)
                adapter = BrainAttempt(
                    controller,
                    controller.next_action(now=0).attempt,
                    self.scope,
                    Budget(40, 3),
                    owners,
                    clock=lambda: 0,
                )
                calls = []
                replies = [
                    self.replies[0],
                    {
                        "tool_calls": [
                            call("submit_flag", {"flag": self.candidate}),
                            call(
                                "submit_flag",
                                {"flag": self.candidate + "second"},
                                "call-2",
                            ),
                        ]
                    },
                ]
                with patch.object(Brain, "_chat", side_effect=replies):
                    result = adapter.run(
                        "fixture",
                        run_bash=lambda _: "evidence",
                        submit_flag=lambda value, calls=calls, verdict=verdict: (
                            calls.append(value) or verdict
                        ),
                    )
                self.assertFalse(result["solved"])
                self.assertEqual(calls, [self.candidate])
                self.assertEqual(
                    controller.snapshot()["work"][0]["state"], "unresolved"
                )
                self.assertEqual(controller.next_action(now=0).kind, DecisionKind.WAIT)

    def test_transport_exception_preserves_intent_and_sanitizes_error(self):
        def lost_response(value):
            self.submissions.append(value)
            raise TimeoutError("synthetic-secret-that-must-not-be-reported")

        result = self.run_attempt(submit=lost_response)
        self.assertEqual(len(self.submissions), 1)
        self.assertEqual(self.row()["state"], "unresolved")
        self.assertEqual(
            self.owners.writes[-1]["controller"]["work"][0]["state"], "unresolved"
        )
        self.assertNotIn("synthetic-secret", repr(result))

    def test_wrong_candidate_is_recorded_and_not_resubmitted_after_changed_approach(
        self,
    ):
        calls = []
        result = self.run_attempt(
            submit=lambda value: calls.append(value) or {"status": "incorrect"}
        )
        self.assertFalse(result["solved"])
        self.assertEqual(self.row()["reason"], "wrong")
        self.controller.propose_approach(
            self.task.scope, "different", "negative-evidence"
        )
        self.decision = self.controller.next_action(now=0)
        self.run_attempt(
            replies=[{"content": self.candidate}],
            submit=lambda value: calls.append(value),
        )
        self.assertEqual(calls, [self.candidate])
        self.assertEqual(self.row()["reason"], "settled_candidate_duplicate")

    def test_already_solved_preserves_harness_projection_without_new_acceptance(self):
        result = self.run_attempt(submit=lambda _: {"status": "already_solved"})
        self.assertTrue(result["solved"])
        self.assertEqual(result["verdict"]["status"], "already_solved")
        self.assertEqual(
            self.row()["reason"], "account_history_requires_owner_verification"
        )
        self.assertEqual(self.row()["state"], "awaiting_candidate")

    def test_shared_step_budget_caps_real_brain_model_calls(self):
        result = self.run_attempt(adapter=self.adapter(budget=Budget(1, 3)))
        self.assertEqual(result["steps"], 1)
        self.assertEqual(len(self.commands), 1)
        self.assertEqual(self.submissions, [])

    def test_shared_submission_budget_prevents_intent_and_transport(self):
        result = self.run_attempt(adapter=self.adapter(budget=Budget(40, 0)))
        self.assertFalse(result["solved"])
        self.assertEqual(self.owners.intents, {})
        self.assertEqual(self.submissions, [])

    def test_tool_budget_is_independent_of_number_of_calls_in_one_model_turn(self):
        controller = Controller(
            started_at=0, limits=ControllerLimits(tool_calls_per_attempt=1)
        )
        controller.update_catalogue([self.task], now=0)
        adapter = BrainAttempt(
            controller,
            controller.next_action(now=0).attempt,
            self.scope,
            Budget(40, 3),
            self.owners,
            clock=lambda: 0,
        )
        result = self.run_attempt(
            adapter=adapter,
            replies=[
                {
                    "tool_calls": [
                        call("run_bash", {"command": "first"}),
                        call("run_bash", {"command": "second"}, "call-2"),
                    ]
                }
            ],
        )
        self.assertEqual(self.commands, ["first"])
        self.assertEqual(result["final"], "tool_allowance_exhausted")

    def test_identical_tool_call_stops_instead_of_repeating_expensive_work(self):
        result = self.run_attempt(
            replies=[
                {
                    "tool_calls": [
                        call("run_bash", {"command": "same"}),
                        call("run_bash", {"command": "same"}, "call-2"),
                    ]
                }
            ]
        )
        self.assertEqual(self.commands, ["same"])
        self.assertEqual(self.row()["state"], "deferred")
        self.assertFalse(result["solved"])

    def test_empty_command_is_repaired_without_calling_tool(self):
        self.run_attempt(replies=[{"tool_calls": [call("run_bash", {})]}])
        self.assertEqual(self.commands, [])
        self.assertEqual(self.row()["repairs"], 1)

    def test_deadline_after_model_prevents_tool_or_submission(self):
        def slow_model(messages):
            self.now = 10
            return self.replies[0]

        result = self.run_attempt(
            replies=slow_model, adapter=self.adapter(budget=Budget(40, 3, 10))
        )
        self.assertFalse(result["solved"])
        self.assertEqual(self.commands, [])
        self.assertEqual(self.submissions, [])
        self.assertEqual(self.trace[-2:], ["release", "checkpoint"])

    def test_cancellation_after_model_prevents_effects_and_flushes(self):
        def cancelled_model(messages):
            self.cancelled = True
            return self.replies[0]

        self.run_attempt(replies=cancelled_model)
        self.assertEqual(self.commands, [])
        self.assertEqual(self.controller.next_action(now=0).kind, DecisionKind.STOP)
        self.assertEqual(self.trace[-2:], ["release", "checkpoint"])

    def test_cancellation_after_reserved_checkpoint_keeps_intent_without_sending(self):
        self.owners.after_checkpoint = self.controller.cancel
        self.run_attempt()
        self.assertEqual(self.submissions, [])
        self.assertEqual(self.row()["state"], "unresolved")
        self.assertEqual(tuple(self.owners.intents.values()), ("reserved",))

    def test_changed_generation_during_tool_discards_old_candidate_route(self):
        newer = challenge_from_shared(
            replace(self.scope, instance_generation="gen-2"), "fixture-authority"
        )

        def changed_tool(command):
            self.controller.update_catalogue([newer], now=0)
            return "old-generation output"

        self.run_attempt(tool=changed_tool)
        self.assertEqual(self.submissions, [])
        self.assertEqual(self.row()["state"], "superseded")
        self.assertEqual(self.controller.next_action(now=0).attempt.scope, newer.scope)

    def test_refusal_is_terminal_without_trying_an_alternate_prompt(self):
        self.run_attempt(
            replies=[{"refusal": "synthetic refusal", "content": self.candidate}]
        )
        self.assertEqual(self.submissions, [])
        self.assertEqual(self.row()["state"], "terminal")
        self.assertFalse(
            self.controller.propose_approach(self.task.scope, "reworded", "same")
        )

    def test_documented_model_rate_limit_is_deferred_to_existing_retry_owner(self):
        failure = Failure(
            FailureKind.RATE_LIMIT,
            Operation.MODEL,
            documented_transient=True,
            retry_after=5,
        )
        adapter = self.adapter(classify_model_failure=lambda _: failure)
        result = self.run_attempt(
            replies=TimeoutError("synthetic transport"), adapter=adapter
        )
        self.assertEqual(result["steps"], 1)
        self.assertEqual(self.row()["ready_at"], 5)
        self.assertEqual(self.controller.next_action(now=0).kind, DecisionKind.WAIT)
        self.assertEqual(self.controller.next_action(now=5).kind, DecisionKind.ATTEMPT)

    def test_default_model_auth_and_configuration_failures_block_unchanged_revision(
        self,
    ):
        response = Response()
        response.status_code = 401
        for failure in (
            ConfigurationError("synthetic missing config"),
            HTTPError(response=response),
        ):
            with self.subTest(failure=type(failure).__name__):
                controller = Controller(started_at=0)
                controller.update_catalogue([self.task], now=0)
                adapter = BrainAttempt(
                    controller,
                    controller.next_action(now=0).attempt,
                    self.scope,
                    Budget(40, 3),
                    self.owners,
                    clock=lambda: 0,
                )
                self.run_attempt(replies=failure, adapter=adapter)
                self.assertEqual(
                    controller.snapshot()["work"][0]["reason"],
                    "unchanged_configuration",
                )
                self.assertFalse(controller.update_configuration("model", "unreported"))
                self.assertTrue(
                    controller.update_configuration("model", "owner-revision-2")
                )

    def test_checkpoint_failure_prevents_send_and_preserves_pending_candidate(self):
        self.owners.fail_checkpoint = True
        result = self.run_attempt()
        self.assertEqual(self.submissions, [])
        self.assertEqual(self.row()["state"], "unresolved")
        self.assertEqual(result["error"], "intent_requires_reconciliation")

    def test_cleanup_failure_does_not_erase_definitive_outcome(self):
        self.owners.fail_release = True
        result = self.run_attempt()
        self.assertTrue(result["solved"])
        self.assertEqual(result["cleanup_errors"], ["resource_release"])
        self.assertEqual(self.trace[-1], "checkpoint")

    def test_interrupt_during_submission_preserves_uncertainty_before_propagating(self):
        def interrupted(value):
            self.submissions.append(value)
            raise KeyboardInterrupt()

        with self.assertRaises(KeyboardInterrupt):
            self.run_attempt(submit=interrupted)
        self.assertEqual(len(self.submissions), 1)
        self.assertEqual(self.row()["state"], "unresolved")
        self.assertEqual(self.controller.next_action(now=0).kind, DecisionKind.STOP)
        self.assertEqual(self.trace[-2:], ["release", "checkpoint"])

    def test_interrupt_during_model_releases_attempt_and_flushes_before_propagating(
        self,
    ):
        with self.assertRaises(KeyboardInterrupt):
            self.run_attempt(replies=KeyboardInterrupt())
        self.assertIsNone(self.controller.snapshot()["active_attempt_token"])
        self.assertEqual(self.controller.snapshot()["metrics"]["model_requests"], 1)
        self.assertEqual(self.controller.next_action(now=0).kind, DecisionKind.STOP)
        self.assertEqual(self.trace[-2:], ["release", "checkpoint"])

    def test_adapter_and_admitted_ownership_cannot_be_reused(self):
        adapter = self.adapter()
        self.run_attempt(adapter=adapter)
        with self.assertRaises(ValueError):
            adapter.run("fixture", run_bash=self.execute_tool, submit_flag=self.submit)
        self.assertEqual(len(self.submissions), 1)
        self.assertEqual(self.trace.count("release"), 1)

    def test_two_adapters_cannot_execute_the_same_live_admission(self):
        second = self.adapter()
        replies = iter(self.replies)

        def model(messages):
            with self.assertRaises(ValueError):
                second.run(
                    "duplicate", run_bash=self.execute_tool, submit_flag=self.submit
                )
            return next(replies)

        self.assertTrue(self.run_attempt(replies=model)["solved"])
        self.assertEqual(len(self.commands), 1)
        self.assertEqual(len(self.submissions), 1)
        self.assertIsNone(self.controller.snapshot()["active_execution_token"])

    def test_foreign_shared_scope_and_forged_attempt_are_rejected_before_execution(
        self,
    ):
        with self.assertRaises(ValueError):
            BrainAttempt(
                self.controller,
                self.decision.attempt,
                replace(self.scope, material_ref="other"),
                Budget(40, 3),
                self.owners,
            )
        adapter = BrainAttempt(
            self.controller,
            replace(self.decision.attempt, token=True),
            self.scope,
            Budget(40, 3),
            self.owners,
            clock=lambda: 0,
        )
        with self.assertRaises(ValueError):
            adapter.run("fixture", run_bash=self.execute_tool, submit_flag=self.submit)
        self.assertEqual(self.trace, [])

    def test_shared_scope_mapping_retains_generation_but_not_parent_attempt_as_material(
        self,
    ):
        renamed = replace(
            self.scope, attempt_id="parent-2", name="Different display name"
        )
        self.assertEqual(
            challenge_from_shared(renamed, "fixture-authority").scope, self.task.scope
        )
        newer = replace(self.scope, instance_generation="gen-2")
        self.assertNotEqual(
            challenge_from_shared(newer, "fixture-authority").scope, self.task.scope
        )

    def test_decision_projects_to_shared_next_action_with_separate_allowances(self):
        action = action_from_decision(self.decision)
        self.assertIsInstance(action, NextAction)
        self.assertEqual(action.kind, "attempt")
        self.assertEqual(action.arguments["model_requests"], 2)
        self.assertEqual(action.arguments["tool_calls"], 4)

    def test_tool_error_mapping_does_not_invent_oom_or_repair_malformed_responses(self):
        for category in (
            FailureCategory.RESOURCE_LIMIT,
            FailureCategory.MALFORMED_RESPONSE,
        ):
            result = ToolResult("action", "observation", (), "", 0, error=category)
            self.assertEqual(failure_from_tool(result).kind, FailureKind.UNKNOWN)
        self.owners.error = FailureCategory.AUTHENTICATION
        self.run_attempt()
        self.assertEqual(self.row()["reason"], "unchanged_configuration")
        self.assertFalse(
            self.controller.propose_approach(self.task.scope, "retry", "same")
        )

    def test_shared_submission_mapping_keeps_already_solved_distinct(self):
        result = submission_from_verdict("intent-1", {"status": "already_solved"})
        self.assertEqual(outcome_from_submission(result).value, "already_solved")
        self.assertTrue(result.definitive)
        self.assertEqual(
            submission_from_verdict("intent-1", None).status, SubmissionStatus.UNCERTAIN
        )


if __name__ == "__main__":
    unittest.main()
