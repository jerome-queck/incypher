import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

from agent_ext.runtime_state import (
    AttemptOutcome,
    ChallengeBrief,
    ChallengeKind,
    MAX_PROJECTION_BYTES,
    MAX_PROJECTION_RECORDS,
    ObservationKind,
    RuntimeState,
    RuntimeStateError,
    Scope,
)
from agent_ext.runtime_context import Finding, FindingDisposition, FindingKind


class RuntimeStateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "state.sqlite3"
        self.store = RuntimeState(self.path)
        self.static = Scope(7, "material-a", ChallengeKind.STATIC)
        self.dynamic = Scope(8, "material-b", ChallengeKind.DYNAMIC, "instance-a")

    @staticmethod
    def finding_context(scope, redaction_values=()):
        return SimpleNamespace(
            challenge_id=scope.challenge_id,
            material_ref=scope.material_hash,
            challenge_type=scope.kind.value,
            instance_generation=scope.instance_hash,
            redaction_values=tuple(redaction_values),
        )

    def test_partial_transaction_rolls_back(self):
        def fail(operation):
            if operation == "checkpoint_outcome":
                raise OSError("fault")

        store = RuntimeState(self.path, before_commit=fail)
        with self.assertRaises(RuntimeStateError):
            store.checkpoint_outcome(self.static, AttemptOutcome.TIMEOUT, now=10)
        ranked = self.store.rank(
            [ChallengeBrief(7, 100, ChallengeKind.STATIC, "material-a")], now=20
        )[0]
        self.assertEqual(ranked.attempts, 0)

    def test_lock_failure_is_bounded_and_sanitized(self):
        lock = sqlite3.connect(self.path, isolation_level=None)
        lock.execute("BEGIN IMMEDIATE")
        self.addCleanup(lock.close)
        store = RuntimeState(self.path, timeout=0.01)
        with self.assertRaisesRegex(RuntimeStateError, "checkpoint_outcome failed"):
            store.checkpoint_outcome(self.static, AttemptOutcome.CRASH)
        lock.execute("ROLLBACK")

    def test_corrupt_and_oversized_rows_are_ignored(self):
        self.store.record_observation(self.static, ObservationKind.TOOL, "valid")
        connection = sqlite3.connect(self.path)
        connection.execute(
            """INSERT INTO observations(scope_key, challenge_id, material_hash,
               challenge_kind, instance_hash, observation_kind, command_fp,
               output_fp, summary, progress, created_at)
               VALUES(?, 7, 'material-a', 'static', NULL, 'finding', NULL, NULL, ?, 0, 2)""",
            (self.static.key, "x" * 600),
        )
        connection.execute(
            "UPDATE challenge_state SET attempts = -1 WHERE scope_key = ?", (self.static.key,)
        )
        connection.commit()
        connection.close()
        projection = self.store.project(self.static)
        self.assertEqual(projection.record_count, 1)
        self.assertIn("valid", projection.text)

    def test_static_and_dynamic_scope_mismatch(self):
        self.store.checkpoint_finding(
            self.finding_context(self.static),
            Finding(FindingKind.OBSERVED, "Static evidence is reusable."),
        )
        self.store.checkpoint_finding(
            self.finding_context(self.dynamic),
            Finding(FindingKind.OBSERVED, "Dynamic evidence is reusable."),
        )
        changed_material = Scope(7, "material-new", ChallengeKind.STATIC)
        changed_instance = Scope(8, "material-b", ChallengeKind.DYNAMIC, "instance-b")
        self.assertEqual(self.store.project(changed_material).record_count, 0)
        self.assertEqual(self.store.project(changed_instance).record_count, 0)

    def test_command_dedupe_is_scope_specific(self):
        self.assertTrue(self.store.record_command(self.static, "id", "uid=1", "identity checked"))
        self.assertTrue(self.store.command_seen(self.static, "id"))
        self.assertFalse(self.store.record_command(self.static, "id", "uid=1", "repeat"))
        other = Scope(9, "material-a", ChallengeKind.STATIC)
        self.assertFalse(self.store.command_seen(other, "id"))

    def test_checkpoint_finding_is_typed_exact_and_scope_specific(self):
        finding = Finding(
            FindingKind.OBSERVED,
            "The decoder applies XOR after reversing each input block.",
        )
        self.assertIs(
            self.store.checkpoint_finding(self.finding_context(self.static), finding, now=1),
            FindingDisposition.SAVED,
        )
        self.assertIs(
            self.store.checkpoint_finding(self.finding_context(self.static), finding, now=2),
            FindingDisposition.DUPLICATE,
        )
        other = Scope(9, "material-a", ChallengeKind.STATIC)
        self.assertIs(
            self.store.checkpoint_finding(self.finding_context(other), finding, now=3),
            FindingDisposition.SAVED,
        )
        self.assertIs(
            self.store.checkpoint_finding(
                self.finding_context(self.static), finding.summary, now=4
            ),
            FindingDisposition.REJECTED,
        )
        projection = self.store.project(self.static)
        self.assertEqual(projection.record_count, 1)
        self.assertIn(finding.summary, projection.text)
        self.assertIn('"progress":1', projection.text)
        self.assertIn('"finding_kind":"observed"', projection.text)
        self.assertIs(
            self.store.checkpoint_finding(self.static, finding, now=5),
            FindingDisposition.REJECTED,
        )

    def test_connection_redaction_term_is_rejected_without_persistence(self):
        class Context:
            challenge_id = 7
            material_ref = "material-a"
            challenge_type = "static"
            instance_generation = None
            redaction_values = ("synthetic-box", "31337")

        finding = Finding(
            FindingKind.HYPOTHESIS,
            "The synthetic-box process may parse length before content.",
        )
        self.assertIs(
            self.store.checkpoint_finding(Context(), finding),
            FindingDisposition.REJECTED,
        )
        self.store.checkpoint()
        payload = b"".join(path.read_bytes() for path in self.path.parent.glob("state.sqlite3*"))
        self.assertNotIn(b"synthetic-box", payload)

    def test_short_case_changed_connection_terms_are_rejected_before_write(self):
        class Context:
            challenge_id = 7
            material_ref = "material-a"
            challenge_type = "static"
            instance_generation = None
            redaction_values = ("nc xy 7",)

        finding = Finding(
            FindingKind.OBSERVED,
            "The route label is XY and stage is 7.",
        )
        self.assertIs(
            self.store.checkpoint_finding(Context(), finding),
            FindingDisposition.REJECTED,
        )
        self.store.checkpoint()
        payload = b"".join(path.read_bytes() for path in self.path.parent.glob("state.sqlite3*"))
        self.assertNotIn(b"route label", payload)

    def test_unlabelled_runtime_credential_value_is_rejected_before_write(self):
        context = self.finding_context(self.static, ("swordfish",))
        finding = Finding(
            FindingKind.OBSERVED,
            "The derived label is SwordFish.",
        )
        self.assertIs(
            self.store.checkpoint_finding(context, finding),
            FindingDisposition.REJECTED,
        )
        self.store.checkpoint()
        payload = b"".join(path.read_bytes() for path in self.path.parent.glob("state.sqlite3*"))
        self.assertNotIn(b"SwordFish", payload)

    def test_projection_is_bounded_and_sanitized(self):
        for index in range(40):
            self.store.record_observation(
                self.static, ObservationKind.TOOL, f"record-{index} " + "x" * 600,
                progress=index,
            )
        projection = self.store.project(self.static)
        self.assertLessEqual(projection.record_count, MAX_PROJECTION_RECORDS)
        self.assertLessEqual(projection.byte_count, MAX_PROJECTION_BYTES)
        self.assertIn("record-39", projection.text)

    def test_ranking_backoff_aging_and_ties_are_deterministic(self):
        briefs = [
            ChallengeBrief(3, 100, ChallengeKind.DYNAMIC, "m3", "i3"),
            ChallengeBrief(2, 100, ChallengeKind.STATIC, "m2"),
            ChallengeBrief(1, 200, ChallengeKind.STATIC, "m1", solved=True),
            ChallengeBrief(4, 100, ChallengeKind.STATIC, "m4"),
        ]
        self.store.checkpoint_outcome(briefs[1].scope, AttemptOutcome.TIMEOUT, now=10)
        self.store.checkpoint_outcome(briefs[3].scope, AttemptOutcome.UNSOLVED, progress_delta=2, now=8)
        first = self.store.rank(briefs, now=10.5)
        second = self.store.rank(briefs, now=10.5)
        self.assertEqual(first, second)
        self.assertEqual([item.brief.challenge_id for item in first], [3, 4, 2, 1])
        self.assertFalse(first[2].eligible)
        self.store.checkpoint_outcome(briefs[1].scope, AttemptOutcome.TIMEOUT, now=12)
        self.assertEqual(self.store.rank(briefs, now=12)[2].backoff_seconds, 2)
        self.assertTrue(any(item.brief.challenge_id == 2 and item.eligible
                            for item in self.store.rank(briefs, now=14)))

    def test_integration_brief_api_returns_original_objects(self):
        briefs = [
            {"id": 2, "points": 100, "type": "standard"},
            {"id": 1, "points": 200, "type": "standard", "solved": True},
        ]
        ordered = self.store.rank_briefs(briefs, now=10)
        self.assertIs(ordered[0], briefs[0])
        self.store.record_challenge_outcome(2, False, 3, "timeout", now=10)
        ordered = self.store.rank_briefs(briefs, now=10.5)
        self.assertIs(ordered[-1], briefs[1])

    def test_catalogue_crowd_solves_prioritize_likely_easy_work(self):
        briefs = [
            {"id": 1, "points": 100, "type": "standard", "solves": 1},
            {"id": 2, "points": 110, "type": "standard", "solve_count": 0},
            {"id": 3, "points": 0, "type": "standard", "solves": 10_000},
        ]
        ordered = self.store.rank_briefs(briefs, now=10)
        self.assertEqual([brief["id"] for brief in ordered], [3, 1, 2])
        self.assertIs(ordered[0], briefs[2])

    def test_easy_first_work_cannot_monopolize_later_passes(self):
        briefs = [
            {"id": 1, "points": 500, "type": "standard", "solves": 0},
            {"id": 2, "points": 100, "type": "standard", "solves": 0},
        ]
        self.assertEqual(self.store.rank_briefs(briefs, now=10)[0]["id"], 2)
        self.store.record_challenge_outcome(2, False, 1, "unsolved", now=10)
        self.assertEqual(self.store.rank_briefs(briefs, now=13)[0]["id"], 1)

    def test_catalogue_crowd_solves_ignores_absent_or_malformed_values(self):
        briefs = [
            {"id": 1, "points": 100, "type": "standard", "solves": True},
            {"id": 2, "points": 100, "type": "standard", "solves": -1},
            {"id": 3, "points": 100, "type": "standard", "solves": "99"},
            {"id": 4, "points": 100, "type": "standard"},
            {
                "id": 5,
                "points": 100,
                "type": "standard",
                "solves": "bad",
                "solve_count": 1,
            },
        ]
        ordered = self.store.rank_briefs(briefs, now=10)
        self.assertEqual([brief["id"] for brief in ordered], [5, 1, 2, 3, 4])

    def test_catalogue_crowd_solves_do_not_change_scope_hash(self):
        low = {"id": 7, "points": 100, "type": "standard", "solves": 1}
        high = {"id": 7, "points": 100, "type": "standard", "solves": 1_000}
        self.assertEqual(
            self.store._brief_adapter(low).scope,
            self.store._brief_adapter(high).scope,
        )

    def test_dynamic_iac_brief_uses_restart_stable_dynamic_rank_scope(self):
        brief = {"id": 8, "points": 500, "type": "dynamic_iac", "solved": False}
        self.assertIs(self.store.rank_briefs([brief], now=10)[0], brief)
        outcome = self.store.record_challenge_outcome(8, False, 1, "timeout", now=10)
        self.assertEqual(outcome.brief.kind, ChallengeKind.DYNAMIC)
        self.assertEqual(outcome.brief.instance_hash, "pending")

    def test_progress_checkpoint_does_not_close_attempt_or_add_backoff(self):
        brief = {"id": 5, "points": 250, "type": "standard", "solved": False}
        self.store.rank_briefs([brief], now=10)
        self.assertEqual(self.store.record_challenge_progress(5, now=10), 1)
        self.assertEqual(self.store.record_challenge_progress(5, 2, now=11), 3)
        ranked = self.store.rank_briefs([brief], now=11)[0]
        self.assertIs(ranked, brief)
        typed = self.store.rank(
            [ChallengeBrief(5, 250, ChallengeKind.STATIC,
                            self.store._brief_adapter(brief).material_hash)], now=11
        )[0]
        self.assertEqual(typed.progress, 3)
        self.assertEqual(typed.attempts, 0)
        self.assertTrue(typed.eligible)

    def test_uncertain_submission_blocks_replay_until_later_catalogue_reconciliation(self):
        brief = {"id": 7, "points": 100, "type": "standard", "solved": False}
        context = self.finding_context(self.static)
        candidate = "INCYPHER{SUBMISSION_SENTINEL}"
        self.store.rank_briefs([brief], now=10)
        self.assertTrue(self.store.reserve_submission(context, candidate, now=10))
        self.assertTrue(
            self.store.mark_submission_dispatch_possible(context, candidate, now=11)
        )
        self.assertFalse(self.store.reserve_submission(context, candidate, now=11))
        self.store.reconcile_submission(context, candidate, "uncertain", now=12)

        self.assertFalse(self.store.submission_reconciled(context))
        self.store.reconcile_submission_catalogue([brief], now=311.999)
        self.assertFalse(self.store.submission_reconciled(context))
        self.store.reconcile_submission_catalogue([brief], now=312)
        self.assertTrue(self.store.submission_reconciled(context))

        self.store.checkpoint()
        payload = b"".join(
            path.read_bytes() for path in self.path.parent.glob("state.sqlite3*")
        )
        self.assertNotIn(b"SUBMISSION_SENTINEL", payload)

    def test_definitive_submission_verdict_clears_intent_immediately(self):
        brief = {"id": 7, "points": 100, "type": "standard", "solved": False}
        context = self.finding_context(self.static)
        self.store.rank_briefs([brief], now=10)
        self.assertTrue(self.store.reserve_submission(context, "INCYPHER{safe}", now=10))
        self.assertTrue(self.store.mark_submission_dispatch_possible(
            context, "INCYPHER{safe}", now=10.5
        ))
        self.store.reconcile_submission(context, "INCYPHER{safe}", "incorrect", now=11)
        self.assertTrue(self.store.submission_reconciled(context))

    def test_dispatch_marker_survives_restart_and_is_scope_exact(self):
        context = self.finding_context(self.static)
        other = self.finding_context(Scope(7, "material-new", ChallengeKind.STATIC))
        candidate = "INCYPHER{possible-effect}"
        self.assertTrue(self.store.reserve_submission(context, candidate, now=10))
        self.assertTrue(
            self.store.mark_submission_dispatch_possible(context, candidate, now=11)
        )

        restarted = RuntimeState(self.path)
        self.assertFalse(restarted.submission_reconciled(context))
        self.assertTrue(restarted.submission_reconciled(other))
        self.assertTrue(restarted.reserve_submission(other, candidate, now=12))

    def test_dispatch_marker_commit_failure_preserves_safe_reservation(self):
        def fail(operation):
            if operation == "mark_submission_dispatch_possible":
                raise OSError("fault")

        context = self.finding_context(self.static)
        candidate = "INCYPHER{marker-not-committed}"
        store = RuntimeState(self.path, before_commit=fail)
        self.assertTrue(store.reserve_submission(context, candidate, now=10))
        with self.assertRaisesRegex(RuntimeStateError, "was not committed"):
            store.mark_submission_dispatch_possible(context, candidate, now=11)

        restarted = RuntimeState(self.path)
        self.assertTrue(restarted.submission_reconciled(context))
        self.assertTrue(restarted.reserve_submission(context, candidate, now=12))

    def test_submission_reservation_commit_failure_fails_before_dispatch(self):
        def fail(operation):
            if operation == "reserve_submission":
                raise OSError("fault")

        store = RuntimeState(self.path, before_commit=fail)
        with self.assertRaisesRegex(RuntimeStateError, "was not committed"):
            store.reserve_submission(
                self.finding_context(self.static), "INCYPHER{never-dispatched}", now=10
            )

        restarted = RuntimeState(self.path)
        brief = {"id": 7, "points": 100, "type": "standard", "solved": False}
        restarted.rank_briefs([brief], now=11)
        self.assertTrue(restarted.submission_reconciled(
            self.finding_context(self.static)
        ))

    def test_restart_and_concurrent_readers(self):
        self.store.record_observation(self.static, ObservationKind.TOOL, "durable")
        restarted = RuntimeState(self.path)
        barrier = threading.Barrier(8)
        errors = []

        def reader():
            try:
                barrier.wait()
                self.assertIn("durable", restarted.project(self.static).text)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=reader) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])

    def test_database_contains_no_raw_sentinels(self):
        command = "curl https://user:pass@host/?token=COMMAND_SENTINEL"
        output = "FLAG{FLAG_SENTINEL} CONNECTION_SENTINEL"
        self.store.record_command(
            self.static, command, output,
            "ran COMMAND_SENTINEL; got FLAG{FLAG_SENTINEL} "
            "CONNECTION_SENTINEL; key=KEY_SENTINEL",
            sensitive_values=("CONNECTION_SENTINEL", "KEY_SENTINEL"),
        )
        self.store.checkpoint()
        payload = b"".join(path.read_bytes() for path in self.path.parent.glob("state.sqlite3*"))
        for sentinel in (
            b"COMMAND_SENTINEL", b"FLAG_SENTINEL", b"CONNECTION_SENTINEL", b"KEY_SENTINEL"
        ):
            self.assertNotIn(sentinel, payload)


if __name__ == "__main__":
    unittest.main()
