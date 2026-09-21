import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

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


class RuntimeStateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "state.sqlite3"
        self.store = RuntimeState(self.path)
        self.static = Scope(7, "material-a", ChallengeKind.STATIC)
        self.dynamic = Scope(8, "material-b", ChallengeKind.DYNAMIC, "instance-a")

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
        self.store.record_observation(self.static, ObservationKind.FINDING, "valid")
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
        self.store.record_observation(self.static, ObservationKind.FINDING, "static evidence")
        self.store.record_observation(self.dynamic, ObservationKind.FINDING, "dynamic evidence")
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

    def test_projection_is_bounded_and_sanitized(self):
        for index in range(40):
            self.store.record_observation(
                self.static, ObservationKind.FINDING, f"record-{index} " + "x" * 600,
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
        self.assertEqual([item.brief.challenge_id for item in first], [4, 3, 2, 1])
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

    def test_dynamic_iac_brief_uses_restart_stable_dynamic_rank_scope(self):
        brief = {"id": 8, "points": 500, "type": "dynamic_iac", "solved": False}
        self.assertIs(self.store.rank_briefs([brief], now=10)[0], brief)
        outcome = self.store.record_challenge_outcome(8, False, 1, "timeout", now=10)
        self.assertEqual(outcome.brief.kind, ChallengeKind.DYNAMIC)
        self.assertEqual(outcome.brief.instance_hash, "pending")

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
