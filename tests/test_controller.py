import hashlib
import socket
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from agent_ext.controller import (
    AttemptReport,
    CandidateOutcome,
    Controller,
    ControllerLimits,
    DecisionKind,
    EvidenceKind,
    Followup,
    ProgressEvidence,
    WorkState,
)
from agent_ext.retry_policy import Failure, FailureKind, Operation
from agent_ext.scheduler import Challenge, Scope, SelectionPolicy


def fingerprint(label):
    return hashlib.sha256(f"synthetic:{label}".encode()).hexdigest()


def challenge(name="a", material="material-1", instance=None, **metadata):
    return Challenge(Scope(name, material, instance), "synthetic-authority", **metadata)


def evidence(
    scope, label="observation-1", confirmed=True, kind=EvidenceKind.OBSERVATION
):
    return ProgressEvidence(scope, fingerprint(label), kind, confirmed)


class ControllerTests(unittest.TestCase):
    def setUp(self):
        self.addCleanup(patch.stopall)
        patch.object(
            socket,
            "socket",
            side_effect=AssertionError("offline test attempted network access"),
        ).start()
        self.controller = Controller(
            started_at=0,
            limits=ControllerLimits(idle_grace_seconds=5, catalogue_poll_seconds=1),
        )

    def begin(self, *items, controller=None, now=0):
        controller = controller or self.controller
        controller.update_catalogue(items or [challenge()], now=now)
        decision = controller.next_action(now=now)
        self.assertEqual(decision.kind, DecisionKind.ATTEMPT)
        return decision.attempt

    def row(self, scope, controller=None):
        controller = controller or self.controller
        return next(
            row for row in controller.snapshot()["work"] if row["scope"] == scope
        )

    def finish(self, attempt, controller=None, now=0, **kwargs):
        controller = controller or self.controller
        return controller.finish_attempt(
            attempt.token, AttemptReport(attempt.scope, **kwargs), now=now
        )

    def test_empty_catalogue_waits_for_updates_then_stops_with_checkpoint(self):
        decision = self.controller.next_action(now=0)
        self.assertEqual(
            (decision.kind, decision.wake_at, decision.refresh_catalogue),
            (DecisionKind.WAIT, 1, True),
        )
        stop = self.controller.next_action(now=5)
        self.assertEqual(stop.kind, DecisionKind.STOP)
        self.assertTrue(stop.checkpoint_required)
        self.assertTrue(stop.release_resources)

    def test_catalogue_arriving_during_idle_grace_is_served(self):
        self.controller.next_action(now=0)
        self.assertEqual(self.begin(challenge("new"), now=2).scope.challenge_id, "new")

    def test_repeated_unchanged_catalogue_does_not_extend_idle_forever(self):
        attempt = self.begin()
        self.finish(attempt)
        self.controller.next_action(now=0)
        self.controller.update_catalogue([challenge()], now=4)
        self.assertEqual(self.controller.next_action(now=5).kind, DecisionKind.STOP)

    def test_one_active_owner_even_with_concurrent_callers(self):
        self.controller.update_catalogue([challenge("a"), challenge("b")], now=0)
        with ThreadPoolExecutor(max_workers=8) as pool:
            decisions = list(
                pool.map(lambda _: self.controller.next_action(now=0), range(16))
            )
        self.assertEqual(
            sum(decision.kind is DecisionKind.ATTEMPT for decision in decisions), 1
        )
        self.assertEqual(self.controller.snapshot()["metrics"]["attempts"], 1)

    def test_stale_or_duplicate_completion_cannot_release_another_lease(self):
        first = self.begin(challenge("a"), challenge("b"))
        self.finish(first)
        second = self.controller.next_action(now=0).attempt
        with self.assertRaises(ValueError):
            self.finish(first)
        with self.assertRaises(ValueError):
            self.controller.finish_attempt(
                second.token, AttemptReport(first.scope), now=0
            )
        self.assertEqual(
            self.controller.snapshot()["active_attempt_token"], second.token
        )

    def test_boolean_cannot_impersonate_attempt_token_one(self):
        first = self.begin()
        with self.assertRaises(ValueError):
            self.controller.finish_attempt(True, AttemptReport(first.scope), now=0)
        self.assertEqual(
            self.controller.snapshot()["active_attempt_token"], first.token
        )

    def test_broad_initial_coverage_before_continuation(self):
        first = self.begin(challenge("a"), challenge("b"), challenge("c"))
        self.finish(first, evidence=(evidence(first.scope),))
        second = self.controller.next_action(now=0).attempt
        self.assertEqual(second.scope.challenge_id, "b")
        self.finish(second)
        third = self.controller.next_action(now=0).attempt
        self.assertEqual(third.scope.challenge_id, "c")
        self.assertEqual(self.controller.snapshot()["metrics"]["scopes_attempted"], 3)

    def test_aged_work_is_served_despite_a_stream_of_fresh_tasks(self):
        controller = Controller(
            started_at=0,
            limits=ControllerLimits(
                max_attempts_per_scope=10, max_continuations_per_approach=8
            ),
        )
        initial = self.begin(challenge("old"), controller=controller)
        self.finish(initial, controller=controller, evidence=(evidence(initial.scope),))
        choices = []
        for index in range(1, 6):
            controller.update_catalogue([challenge(f"new-{index}")], now=0)
            attempt = controller.next_action(now=0).attempt
            choices.append(attempt.scope.challenge_id)
            self.finish(attempt, controller=controller)
        self.assertIn("old", choices[:4])

    def test_one_failed_task_does_not_stop_unrelated_work(self):
        first = self.begin(challenge("a"), challenge("b"))
        self.finish(first, failure=Failure(FailureKind.UNKNOWN, Operation.TOOL))
        self.assertEqual(
            self.controller.next_action(now=0).attempt.scope.challenge_id, "b"
        )

    def test_identical_observations_never_earn_unlimited_continuations(self):
        first = self.begin()
        proof = evidence(first.scope)
        self.finish(first, evidence=(proof,))
        second = self.controller.next_action(now=0).attempt
        self.finish(second, evidence=(proof,))
        self.assertEqual(self.row(first.scope)["reason"], "no_new_evidence")
        for _ in range(5):
            self.assertFalse(self.controller.observe_evidence(first.scope, (proof,)))
            self.assertEqual(self.controller.next_action(now=0).kind, DecisionKind.WAIT)
        self.assertEqual(self.controller.snapshot()["metrics"]["attempts"], 2)

    def test_unconfirmed_or_other_scope_evidence_is_not_progress(self):
        first = self.begin()
        self.finish(
            first,
            evidence=(
                evidence(first.scope, confirmed=False),
                evidence(Scope("other", "m")),
            ),
        )
        self.assertEqual(self.row(first.scope)["reason"], "no_new_evidence")
        self.assertEqual(self.row(first.scope)["progress_fingerprints"], ())

    def test_new_evidence_can_reenable_stalled_work_without_erasing_history(self):
        first = self.begin()
        self.finish(first)
        failures = self.row(first.scope)["failures"]
        self.assertTrue(
            self.controller.observe_evidence(first.scope, (evidence(first.scope),))
        )
        self.assertEqual(self.controller.next_action(now=0).kind, DecisionKind.ATTEMPT)
        self.assertEqual(self.row(first.scope)["failures"], failures)

    def test_justified_changed_approach_preserves_attempts_and_failure_history(self):
        first = self.begin()
        self.finish(first, failure=Failure(FailureKind.TOOL_OOM, Operation.TOOL))
        failures = self.row(first.scope)["failures"]
        self.assertFalse(
            self.controller.propose_approach(first.scope, "triage", "same-test")
        )
        self.assertTrue(
            self.controller.propose_approach(
                first.scope, "small-window", "measured-cost-1"
            )
        )
        second = self.controller.next_action(now=0).attempt
        self.assertEqual(second.approach_ref, "small-window")
        self.assertEqual(
            self.row(first.scope)["approach_justifications"],
            (("small-window", "measured-cost-1"),),
        )
        self.assertEqual(self.row(first.scope)["attempts"], 2)
        self.assertEqual(self.row(first.scope)["failures"], failures)

    def test_even_distinct_successful_observations_have_a_continuation_cap(self):
        first = self.begin()
        self.finish(first, evidence=(evidence(first.scope, "first"),))
        second = self.controller.next_action(now=0).attempt
        self.finish(second, evidence=(evidence(second.scope, "second"),))
        self.assertEqual(
            self.row(first.scope)["reason"], "continuation_allowance_exhausted"
        )
        self.assertFalse(
            self.controller.observe_evidence(
                first.scope, (evidence(first.scope, "third"),)
            )
        )

    def test_changed_approaches_cannot_reset_finite_attempt_allowance(self):
        first = self.begin()
        attempt = first
        for index in range(4):
            self.finish(attempt)
            if index < 3:
                self.assertTrue(
                    self.controller.propose_approach(
                        first.scope, f"approach-{index}", "justified"
                    )
                )
                attempt = self.controller.next_action(now=0).attempt
        self.assertEqual(self.row(first.scope)["state"], WorkState.TERMINAL.value)
        self.assertFalse(
            self.controller.propose_approach(first.scope, "one-more", "justified")
        )

    def test_rate_limit_wait_allows_other_work_and_uses_finite_retry_allowance(self):
        first = self.begin(challenge("a"), challenge("b"))
        failure = Failure(
            FailureKind.RATE_LIMIT,
            Operation.MODEL,
            documented_transient=True,
            retry_after=2,
        )
        self.finish(first, failure=failure)
        second = self.controller.next_action(now=0).attempt
        self.assertEqual(second.scope.challenge_id, "b")
        self.finish(second)
        self.assertEqual(self.controller.next_action(now=0).wake_at, 1)
        retry = self.controller.next_action(now=2).attempt
        self.finish(retry, now=2, failure=failure)
        retry = self.controller.next_action(now=4).attempt
        self.finish(retry, now=4, failure=failure)
        self.assertEqual(self.row(first.scope)["reason"], "retry_allowance_exhausted")
        self.assertEqual(self.controller.snapshot()["metrics"]["retries"], 2)

    def test_known_future_retry_is_not_cut_off_by_idle_grace(self):
        first = self.begin()
        self.finish(
            first,
            failure=Failure(
                FailureKind.RATE_LIMIT,
                Operation.MODEL,
                documented_transient=True,
                retry_after=20,
            ),
        )
        for tick in range(20):
            decision = self.controller.next_action(now=tick)
            self.assertEqual(decision.kind, DecisionKind.WAIT)
            self.assertGreater(decision.wake_at, tick)
        self.assertEqual(self.controller.next_action(now=20).kind, DecisionKind.ATTEMPT)

    def test_cancellation_during_defer_stops_without_admitting_retry(self):
        first = self.begin()
        self.finish(
            first,
            failure=Failure(
                FailureKind.RATE_LIMIT,
                Operation.MODEL,
                documented_transient=True,
                retry_after=10,
            ),
        )
        self.controller.cancel()
        self.assertEqual(self.controller.next_action(now=1).kind, DecisionKind.STOP)
        self.assertEqual(self.controller.snapshot()["metrics"]["attempts"], 1)

    def test_deadline_during_defer_stops_instead_of_replaying(self):
        controller = Controller(started_at=0, limits=ControllerLimits(run_seconds=3))
        first = self.begin(controller=controller)
        self.finish(
            first,
            controller=controller,
            failure=Failure(
                FailureKind.TRANSIENT,
                Operation.READ,
                documented_transient=True,
                retry_after=2,
            ),
        )
        self.assertEqual(controller.next_action(now=3).kind, DecisionKind.STOP)
        self.assertEqual(controller.snapshot()["metrics"]["attempts"], 1)

    def test_configuration_failure_blocks_only_dependent_work_until_revision_changes(
        self,
    ):
        first = self.begin(
            challenge("a", requires=frozenset({"model"})),
            challenge("b", requires=frozenset({"model"})),
            challenge("c"),
        )
        self.finish(
            first,
            failure=Failure(
                FailureKind.AUTHENTICATION,
                Operation.MODEL,
                subsystem="model",
                configuration_revision="v1",
            ),
        )
        self.assertFalse(self.controller.update_configuration("model", "v1"))
        self.assertFalse(self.controller.propose_approach(first.scope, "new", "reason"))
        independent = self.controller.next_action(now=0).attempt
        self.assertEqual(independent.scope.challenge_id, "c")
        self.finish(independent)
        self.assertEqual(self.controller.next_action(now=0).kind, DecisionKind.WAIT)
        self.assertTrue(self.controller.update_configuration("model", "v2"))
        self.assertEqual(
            self.controller.next_action(now=0).attempt.scope.challenge_id, "b"
        )

    def test_repairs_preserve_authority_and_do_not_repeat_indefinitely(self):
        first = self.begin()
        failure = Failure(FailureKind.MALFORMED_REQUEST, Operation.TOOL)
        self.finish(first, failure=failure)
        repair = self.controller.next_action(now=0).attempt
        self.assertTrue(repair.repair)
        self.assertEqual(
            (repair.scope, repair.authority_ref, repair.approach_ref),
            (first.scope, first.authority_ref, first.approach_ref),
        )
        self.finish(repair, failure=failure)
        self.assertEqual(self.controller.next_action(now=0).kind, DecisionKind.WAIT)

    def test_mutation_failures_cannot_requeue_via_changed_approach(self):
        for operation in (Operation.SUBMISSION, Operation.INSTANCE_MUTATION):
            with self.subTest(operation=operation):
                controller = Controller(started_at=0)
                attempt = self.begin(controller=controller)
                result = self.finish(
                    attempt,
                    controller=controller,
                    failure=Failure(
                        FailureKind.RATE_LIMIT, operation, documented_transient=True
                    ),
                )
                self.assertEqual(result.state, WorkState.UNRESOLVED)
                self.assertFalse(
                    controller.propose_approach(
                        attempt.scope, "retry", "same-operation"
                    )
                )
                self.assertEqual(controller.next_action(now=0).kind, DecisionKind.WAIT)
                controller.reconciled_effect(
                    attempt.scope, resolution_ref="owner-resolution-1"
                )
                self.assertEqual(controller.next_action(now=0).kind, DecisionKind.WAIT)

    def test_stale_instance_requires_owner_requalification_or_new_scope(self):
        first = self.begin(challenge(instance="generation-1"))
        transition = self.finish(
            first, failure=Failure(FailureKind.STALE_INSTANCE, Operation.READ)
        )
        self.assertEqual(transition.followup, Followup.REQUALIFY)
        self.assertFalse(self.controller.propose_approach(first.scope, "new", "reason"))
        self.assertFalse(
            self.controller.requalified(first.scope, revision="generation-1")
        )
        self.assertTrue(
            self.controller.requalified(first.scope, revision="owner-proof-2")
        )
        self.assertEqual(self.controller.next_action(now=0).kind, DecisionKind.ATTEMPT)

    def test_material_and_instance_changes_invalidate_old_evidence(self):
        for newer in (
            challenge(material="material-2"),
            challenge(instance="generation-2"),
        ):
            with self.subTest(newer=newer.scope):
                controller = Controller(started_at=0)
                old = self.begin(controller=controller)
                self.finish(old, controller=controller, evidence=(evidence(old.scope),))
                controller.update_catalogue([newer], now=0)
                self.assertEqual(
                    self.row(newer.scope, controller)["progress_fingerprints"], ()
                )
                current = controller.next_action(now=0).attempt
                self.finish(
                    current, controller=controller, evidence=(evidence(old.scope),)
                )
                self.assertEqual(
                    self.row(newer.scope, controller)["reason"], "no_new_evidence"
                )

    def test_scope_replacement_cancels_old_owner_before_admitting_new_attempt(self):
        old = self.begin()
        newer = challenge(material="material-2")
        self.controller.update_catalogue([newer], now=1)
        cleanup = self.controller.next_action(now=1)
        self.assertEqual(cleanup.cancel_attempt_token, old.token)
        self.assertTrue(cleanup.release_resources)
        transition = self.finish(old, now=1, candidate_ref=fingerprint("old-candidate"))
        self.assertEqual(transition.state, WorkState.SUPERSEDED)
        self.assertEqual(transition.followup, Followup.NONE)
        self.assertEqual(self.controller.next_action(now=1).attempt.scope, newer.scope)

    def test_ambiguous_old_generation_is_preserved_and_blocks_unchanged_challenge(self):
        old = self.begin()
        newer = challenge(material="material-2")
        self.controller.update_catalogue([newer], now=1)
        result = self.finish(
            old,
            now=1,
            failure=Failure(FailureKind.AMBIGUOUS_SUBMISSION, Operation.SUBMISSION),
        )
        self.assertEqual(result.state, WorkState.UNRESOLVED)
        self.assertEqual(self.controller.next_action(now=1).kind, DecisionKind.WAIT)
        self.controller.reconciled_effect(old.scope, resolution_ref="owner-reconciled")
        self.assertEqual(self.controller.next_action(now=1).attempt.scope, newer.scope)

    def test_catalogue_cannot_resurrect_retired_scope_or_change_authority_silently(
        self,
    ):
        self.controller.update_catalogue([challenge()], now=0)
        with self.assertRaises(ValueError):
            self.controller.update_catalogue(
                [Challenge(challenge().scope, "different-authority")], now=0
            )
        self.controller.update_catalogue([challenge(material="material-2")], now=0)
        with self.assertRaises(ValueError):
            self.controller.update_catalogue([challenge()], now=0)

    def test_candidate_is_handed_to_owner_not_automatically_accepted(self):
        first = self.begin()
        candidate = fingerprint("candidate")
        handoff = self.finish(first, candidate_ref=candidate)
        self.assertEqual(handoff.followup, Followup.QUALIFY_CANDIDATE)
        self.assertEqual(handoff.state, WorkState.AWAITING_CANDIDATE)
        self.assertEqual(self.controller.next_action(now=0).kind, DecisionKind.WAIT)

    def test_same_settled_wrong_candidate_is_never_handed_off_again(self):
        first = self.begin()
        candidate = fingerprint("wrong-candidate")
        self.finish(first, candidate_ref=candidate)
        self.controller.resolve_candidate(
            first.scope, candidate, CandidateOutcome.WRONG
        )
        self.controller.propose_approach(
            first.scope, "different-experiment", "negative-evidence"
        )
        second = self.controller.next_action(now=0).attempt
        duplicate = self.finish(second, candidate_ref=candidate)
        self.assertEqual(duplicate.followup, Followup.NONE)
        self.assertEqual(duplicate.reason, "settled_candidate_duplicate")

    def test_ambiguous_candidate_survives_stop_and_only_owner_can_resolve_it(self):
        first = self.begin()
        candidate = fingerprint("candidate")
        self.finish(first, candidate_ref=candidate)
        result = self.controller.resolve_candidate(
            first.scope, candidate, CandidateOutcome.AMBIGUOUS
        )
        self.assertEqual(result.followup, Followup.RECONCILE)
        self.assertFalse(
            self.controller.propose_approach(first.scope, "retry", "reason")
        )
        self.controller.cancel()
        self.assertTrue(self.controller.next_action(now=1).checkpoint_required)
        self.assertEqual(self.row(first.scope)["pending_candidate"], candidate)
        result = self.controller.resolve_candidate(
            first.scope, candidate, CandidateOutcome.ACCEPTED
        )
        self.assertEqual(result.state, WorkState.TERMINAL)
        self.assertEqual(self.controller.next_action(now=1).kind, DecisionKind.STOP)

    def test_already_solved_is_not_promoted_to_current_acceptance(self):
        first = self.begin()
        candidate = fingerprint("candidate")
        self.finish(first, candidate_ref=candidate)
        result = self.controller.resolve_candidate(
            first.scope, candidate, CandidateOutcome.ALREADY_SOLVED
        )
        self.assertEqual(result.state, WorkState.AWAITING_CANDIDATE)
        self.assertNotEqual(result.reason, CandidateOutcome.ACCEPTED.value)

    def test_qualification_rejection_cannot_clear_ambiguous_submission(self):
        first = self.begin()
        candidate = fingerprint("candidate")
        self.finish(first, candidate_ref=candidate)
        self.controller.resolve_candidate(
            first.scope, candidate, CandidateOutcome.AMBIGUOUS
        )
        with self.assertRaises(ValueError):
            self.controller.resolve_candidate(
                first.scope, candidate, CandidateOutcome.QUALIFICATION_REJECTED
            )
        row = self.row(first.scope)
        self.assertEqual(
            (row["state"], row["pending_candidate"]), ("unresolved", candidate)
        )
        self.assertFalse(self.controller.propose_approach(first.scope, "new", "proof"))

    def test_definitive_non_delivery_defers_until_a_justified_new_approach(self):
        first = self.begin()
        candidate = fingerprint("candidate")
        self.finish(first, candidate_ref=candidate)
        self.controller.resolve_candidate(
            first.scope, candidate, CandidateOutcome.AMBIGUOUS
        )
        result = self.controller.resolve_candidate(
            first.scope, candidate, CandidateOutcome.NOT_DELIVERED
        )
        self.assertEqual(result.state, WorkState.DEFERRED)
        self.assertIsNone(self.row(first.scope)["pending_candidate"])
        self.assertEqual(self.controller.next_action(now=0).kind, DecisionKind.WAIT)

    def test_provider_refusal_stops_route_without_disguised_retries(self):
        first = self.begin()
        self.finish(first, failure=Failure(FailureKind.SAFETY_REFUSAL, Operation.MODEL))
        self.assertFalse(
            self.controller.propose_approach(first.scope, "reworded", "same-operation")
        )
        self.assertFalse(
            self.controller.observe_evidence(first.scope, (evidence(first.scope),))
        )
        self.assertEqual(self.row(first.scope)["state"], WorkState.TERMINAL.value)

    def test_cancellation_keeps_active_owner_until_cleanup_report(self):
        first = self.begin()
        self.controller.cancel()
        stop = self.controller.next_action(now=1)
        self.assertEqual(stop.cancel_attempt_token, first.token)
        self.assertTrue(stop.checkpoint_required)
        self.assertTrue(stop.release_resources)
        self.finish(first, now=1)
        self.assertIsNone(self.controller.next_action(now=1).cancel_attempt_token)

    def test_attempt_deadline_requires_cleanup_before_reusing_slot(self):
        first = self.begin(challenge("a"), challenge("b"))
        decision = self.controller.next_action(now=first.deadline)
        self.assertEqual(decision.cancel_attempt_token, first.token)
        self.assertTrue(decision.release_resources)
        self.finish(first, now=first.deadline + 1)
        self.assertEqual(
            self.controller.next_action(
                now=first.deadline + 1
            ).attempt.scope.challenge_id,
            "b",
        )

    def test_attempt_budget_is_capped_by_remaining_run_and_separate_resource_limits(
        self,
    ):
        controller = Controller(
            started_at=0,
            limits=ControllerLimits(
                run_seconds=10, max_model_requests=1, max_tool_calls=2
            ),
        )
        attempt = self.begin(controller=controller, now=8)
        self.assertEqual(
            (
                attempt.budget.seconds,
                attempt.budget.model_requests,
                attempt.budget.tool_calls,
            ),
            (2, 1, 2),
        )

    def test_candidate_at_exact_attempt_deadline_is_not_admitted_to_qualification(self):
        first = self.begin()
        cleanup = self.controller.next_action(now=first.deadline)
        self.assertEqual(cleanup.cancel_attempt_token, first.token)
        result = self.finish(
            first, now=first.deadline, candidate_ref=fingerprint("late")
        )
        self.assertEqual(result.reason, "attempt_budget_exceeded")
        self.assertEqual(result.followup, Followup.NONE)

    def test_reported_resource_overrun_is_not_rewarded_with_candidate_handoff(self):
        first = self.begin()
        result = self.finish(
            first,
            candidate_ref=fingerprint("candidate"),
            tool_calls=first.budget.tool_calls + 1,
        )
        self.assertEqual(
            (result.reason, result.followup), ("attempt_budget_exceeded", Followup.NONE)
        )

    def test_global_model_budget_does_not_disable_scripted_work(self):
        controller = Controller(
            started_at=0, limits=ControllerLimits(max_model_requests=1)
        )
        first = self.begin(
            challenge("a", requires=frozenset({"model"})),
            challenge("b", requires=frozenset({"model"})),
            challenge("c"),
            controller=controller,
        )
        self.finish(first, controller=controller, model_requests=1)
        self.assertEqual(controller.next_action(now=0).attempt.scope.challenge_id, "c")

    def test_zero_per_attempt_allowance_blocks_only_work_requiring_that_resource(self):
        for subsystem, setting in (
            ("model", "model_requests_per_attempt"),
            ("tools", "tool_calls_per_attempt"),
        ):
            with self.subTest(subsystem=subsystem):
                controller = Controller(
                    started_at=0, limits=ControllerLimits(**{setting: 0})
                )
                attempt = self.begin(
                    challenge("a", requires=frozenset({subsystem})),
                    challenge("b"),
                    controller=controller,
                )
                self.assertEqual(attempt.scope.challenge_id, "b")

    def test_finite_admission_cap_and_invalid_clock(self):
        controller = Controller(
            started_at=0, limits=ControllerLimits(max_total_attempts=1)
        )
        first = self.begin(controller=controller)
        self.finish(first, controller=controller, now=1)
        self.assertEqual(
            controller.next_action(now=1).reason, "admission_budget_exhausted"
        )
        with self.assertRaises(ValueError):
            controller.next_action(now=0)

    def test_decisions_include_wait_and_stop_without_double_counting(self):
        self.controller.next_action(now=0)
        self.controller.next_action(now=5)
        self.assertEqual(self.controller.snapshot()["metrics"]["decisions"], 2)
        self.assertEqual(self.controller.snapshot()["metrics"]["attempts"], 0)

    def test_catalogue_and_report_references_are_bounded(self):
        controller = Controller(started_at=0, limits=ControllerLimits(max_scopes=1))
        with self.assertRaises(ValueError):
            controller.update_catalogue([challenge("a"), challenge("b")], now=0)
        with self.assertRaises(ValueError):
            AttemptReport(
                challenge().scope,
                evidence=tuple(evidence(challenge().scope, str(i)) for i in range(33)),
            )


class FakeOwners:
    """Test-only owner adapters; these signatures are NOT the shared contract.

    One step of a fake existing harness consumes a controller decision. In-memory
    intent checkpoints stand in for Richard's durable write-before-send ledger.
    """

    def __init__(self, outcome):
        self.outcome = outcome
        self.trace = []
        self.intents = {}
        self.submitted = set()
        self.writes = []

    def execute(self, attempt):
        if attempt.budget.model_requests < 1 or attempt.budget.tool_calls < 1:
            raise AssertionError("fixture exceeds admitted resource budget")
        self.trace.append("execute_bounded_attempt")
        return AttemptReport(
            attempt.scope,
            evidence=(evidence(attempt.scope),),
            candidate_ref=fingerprint("synthetic-candidate"),
            model_requests=1,
            tool_calls=1,
        )

    def qualify(self, report):
        self.trace.append("qualify")
        # Only a fixture prerequisite, not an implementation of Richard's rules.
        return any(
            item.confirmed and item.scope == report.scope for item in report.evidence
        )

    def reserve(self, scope, candidate_ref):
        key = (scope, candidate_ref)
        if key in self.intents:
            raise AssertionError("duplicate submission intent")
        self.intents[key] = "reserved"
        self.trace.append("reserve_intent")
        return key

    def checkpoint(self, controller, phase):
        self.writes.append(
            {"controller": controller.snapshot(), "intents": dict(self.intents)}
        )
        self.trace.append(
            "flush_projection" if phase == "final" else f"checkpoint_{phase}"
        )

    def submit(self, key):
        if key in self.submitted or self.writes[-1]["intents"].get(key) != "reserved":
            raise AssertionError("intent must be checkpointed and sent at most once")
        self.submitted.add(key)
        self.trace.append("submit_once")
        return self.outcome

    def record_outcome(self, key, outcome):
        self.intents[key] = outcome.value
        self.trace.append("record_outcome")

    def release(self):
        self.trace.append("release_owned_resources")

    def step(self, controller, now):
        decision = controller.next_action(now=now)
        if decision.kind is DecisionKind.ATTEMPT:
            report = self.execute(decision.attempt)
            transition = controller.finish_attempt(
                decision.attempt.token, report, now=now
            )
            if transition.followup is Followup.QUALIFY_CANDIDATE:
                if self.qualify(report):
                    key = self.reserve(report.scope, transition.candidate_ref)
                    self.checkpoint(controller, "intent")
                    outcome = self.submit(key)
                    self.record_outcome(key, outcome)
                else:
                    outcome = CandidateOutcome.QUALIFICATION_REJECTED
                transition = controller.resolve_candidate(
                    report.scope, transition.candidate_ref, outcome
                )
            if transition.checkpoint_required:
                self.checkpoint(controller, "outcome")
        elif decision.kind is DecisionKind.STOP:
            if decision.release_resources:
                self.release()
            if decision.checkpoint_required:
                self.checkpoint(controller, "final")
        return decision


class FakeLifecycleTests(unittest.TestCase):
    def setUp(self):
        blocker = patch.object(
            socket, "socket", side_effect=AssertionError("unexpected network")
        )
        blocker.start()
        self.addCleanup(blocker.stop)

    def test_one_fake_lifecycle_has_one_owner_submitter_writer_and_cleanup(self):
        controller = Controller(
            started_at=0, limits=ControllerLimits(idle_grace_seconds=1)
        )
        controller.update_catalogue([challenge("fixture")], now=0)
        owners = FakeOwners(CandidateOutcome.ACCEPTED)
        owners.step(controller, 0)
        self.assertEqual(owners.step(controller, 0).kind, DecisionKind.WAIT)
        self.assertEqual(owners.step(controller, 1).kind, DecisionKind.STOP)
        self.assertEqual(
            owners.trace,
            [
                "execute_bounded_attempt",
                "qualify",
                "reserve_intent",
                "checkpoint_intent",
                "submit_once",
                "record_outcome",
                "checkpoint_outcome",
                "release_owned_resources",
                "flush_projection",
            ],
        )
        self.assertEqual(len(owners.writes), 3)
        final = owners.writes[-1]["controller"]
        self.assertEqual(final["work"][0]["reason"], "accepted")
        self.assertEqual(final["metrics"]["attempts"], 1)

    def test_fake_ambiguous_submission_is_not_replayed_across_polls_or_stop(self):
        controller = Controller(
            started_at=0, limits=ControllerLimits(idle_grace_seconds=2)
        )
        controller.update_catalogue([challenge("fixture")], now=0)
        owners = FakeOwners(CandidateOutcome.AMBIGUOUS)
        owners.step(controller, 0)
        owners.step(controller, 0)
        for now in (0.5, 1, 1.5):
            self.assertEqual(owners.step(controller, now).kind, DecisionKind.WAIT)
        self.assertEqual(owners.step(controller, 2).kind, DecisionKind.STOP)
        self.assertEqual(len(owners.submitted), 1)
        final = owners.writes[-1]
        self.assertEqual(final["controller"]["work"][0]["state"], "unresolved")
        self.assertEqual(tuple(final["intents"].values()), ("ambiguous",))

    def test_synthetic_policy_comparison_reports_coverage_not_competition_score(self):
        measurements = {}
        for policy in (
            SelectionPolicy.COVERAGE,
            SelectionPolicy.PROGRESS,
            SelectionPolicy.BENEFIT_COST,
        ):
            controller = Controller(
                started_at=0,
                limits=ControllerLimits(selection=policy, idle_grace_seconds=1),
            )
            controller.update_catalogue(
                [challenge(f"task-{i:02}") for i in range(12)], now=0
            )
            scopes = []
            for _ in range(12):
                attempt = controller.next_action(now=0).attempt
                scopes.append(attempt.scope)
                controller.finish_attempt(
                    attempt.token, AttemptReport(attempt.scope), now=0
                )
            controller.next_action(now=0)
            self.assertEqual(controller.next_action(now=1).kind, DecisionKind.STOP)
            measurements[policy.value] = controller.snapshot()["metrics"]
            self.assertEqual(len(set(scopes)), 12)
            self.assertEqual(measurements[policy.value]["attempts"], 12)
            self.assertEqual(measurements[policy.value]["retries"], 0)
            self.assertEqual(measurements[policy.value]["decisions"], 14)


if __name__ == "__main__":
    unittest.main()
