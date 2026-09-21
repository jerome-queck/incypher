import tempfile
import threading
import unittest
from dataclasses import replace
from pathlib import Path

from agent_ext.memory import EvidenceScope
from agent_ext.submission_state import (
    AdapterOutcome,
    IntentState,
    OutcomeEvent,
    RecoveryDisposition,
    StorageCommitError,
    StoragePressure,
    SubmissionStateStore,
)
from agent_ext.verification import DuplicateDisposition


class SubmissionStateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "private-state.sqlite3"
        self.store = SubmissionStateStore(self.path)
        self.scope = EvidenceScope(
            "run-1", "solve", 12, "material-a", "attempt-1", "instance-1"
        )
        self.candidate = b"FLAG{synthetic-one}"

    def dispatched(self, candidate=None):
        reservation = self.store.reserve(self.scope, candidate or self.candidate)
        self.assertTrue(self.store.mark_dispatch_possible(reservation.intent_id))
        return reservation

    def test_r07_concurrent_reservation_and_dispatch_has_one_path(self):
        barrier = threading.Barrier(12)
        reservations = []
        errors = []

        def worker(index):
            try:
                barrier.wait()
                scope = replace(self.scope, attempt_id=f"attempt-{index}")
                reservations.append(self.store.reserve(scope, self.candidate))
            except Exception as exc:  # pragma: no cover - asserted below
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(index,)) for index in range(12)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(sum(item.created for item in reservations), 1)
        self.assertEqual(len({item.intent_id for item in reservations}), 1)

        dispatch_results = []
        barrier = threading.Barrier(12)

        def dispatch():
            barrier.wait()
            dispatch_results.append(
                self.store.mark_dispatch_possible(reservations[0].intent_id)
            )

        threads = [threading.Thread(target=dispatch) for _ in range(12)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sum(dispatch_results), 1)

    def test_r08_crash_boundaries_have_distinct_recovery_states(self):
        self.assertEqual(self.store.recover(None), RecoveryDisposition.NO_INTENT)
        reservation = self.store.reserve(self.scope, self.candidate)
        self.assertTrue(self.store.prove_not_sent(reservation.intent_id))
        self.assertEqual(
            self.store.recover(reservation.intent_id),
            RecoveryDisposition.PROVEN_NOT_SENT,
        )
        self.assertTrue(self.store.mark_dispatch_possible(reservation.intent_id))
        self.assertEqual(
            self.store.recover(reservation.intent_id), RecoveryDisposition.RECONCILE
        )
        self.assertFalse(self.store.prove_not_sent(reservation.intent_id))

    def test_r09_lost_ack_remains_unknown_across_restart_and_is_not_reopened(self):
        reservation = self.dispatched()
        snapshot = self.store.record_outcome(
            reservation.intent_id,
            OutcomeEvent(
                "event-timeout",
                AdapterOutcome.UNKNOWN,
                authoritative=False,
                attributable=False,
            ),
        )
        self.assertEqual(snapshot.state, IntentState.UNKNOWN)
        restarted = SubmissionStateStore(self.path)
        duplicate = restarted.reserve(
            replace(self.scope, attempt_id="attempt-after-restart"), self.candidate
        )
        self.assertFalse(duplicate.dispatch_allowed)
        self.assertEqual(duplicate.intent_id, reservation.intent_id)
        self.assertEqual(
            restarted.recover(duplicate.intent_id), RecoveryDisposition.RECONCILE
        )

    def test_r10_wrong_suppresses_exact_repeat_but_not_distinct_bytes(self):
        reservation = self.dispatched()
        self.store.record_outcome(
            reservation.intent_id,
            OutcomeEvent("event-wrong", AdapterOutcome.WRONG, True, True),
        )
        same = self.store.reserve(
            replace(self.scope, attempt_id="new-approach"), self.candidate
        )
        self.assertFalse(same.dispatch_allowed)
        self.assertEqual(
            self.store.duplicate_disposition(self.scope, self.candidate),
            DuplicateDisposition.WRONG,
        )
        different = self.store.reserve(self.scope, self.candidate + b" ")
        self.assertTrue(different.created)
        self.assertNotEqual(different.intent_id, reservation.intent_id)

    def test_r10_account_already_solved_does_not_accept_this_candidate(self):
        reservation = self.dispatched()
        snapshot = self.store.record_outcome(
            reservation.intent_id,
            OutcomeEvent(
                "event-account",
                AdapterOutcome.ACCOUNT_ALREADY_SOLVED,
                authoritative=True,
                attributable=False,
            ),
        )
        self.assertEqual(snapshot.state, IntentState.RECONCILE)
        self.assertEqual(self.store.diagnostics()["live_successes"], 0)

    def test_r11_replayed_events_are_idempotent_and_timeout_cannot_erase_acceptance(self):
        reservation = self.dispatched()
        accepted = OutcomeEvent(
            "event-accepted", AdapterOutcome.ACCEPTED, True, True
        )
        first = self.store.record_outcome(reservation.intent_id, accepted)
        second = self.store.record_outcome(reservation.intent_id, accepted)
        self.assertEqual(first.event_count, 1)
        self.assertEqual(second.event_count, 1)
        delayed = self.store.record_outcome(
            reservation.intent_id,
            OutcomeEvent("event-late-timeout", AdapterOutcome.UNKNOWN, False, False),
        )
        self.assertEqual(delayed.state, IntentState.ACCEPTED)
        self.assertEqual(delayed.event_count, 2)
        self.assertEqual(self.store.diagnostics()["live_successes"], 1)

    def test_r11_contradictory_authoritative_outcomes_require_reconciliation(self):
        reservation = self.dispatched()
        self.store.record_outcome(
            reservation.intent_id,
            OutcomeEvent("event-accepted", AdapterOutcome.ACCEPTED, True, True),
        )
        conflict = self.store.record_outcome(
            reservation.intent_id,
            OutcomeEvent("event-wrong", AdapterOutcome.WRONG, True, True),
        )
        self.assertEqual(conflict.state, IntentState.CONFLICT)
        self.assertEqual(
            self.store.recover(reservation.intent_id), RecoveryDisposition.RECONCILE
        )

    def test_r14_synthetic_acceptance_never_counts_as_live_success(self):
        reservation = self.dispatched()
        snapshot = self.store.record_outcome(
            reservation.intent_id,
            OutcomeEvent(
                "event-synthetic",
                AdapterOutcome.ACCEPTED,
                authoritative=True,
                attributable=True,
                synthetic=True,
            ),
        )
        self.assertEqual(snapshot.state, IntentState.ACCEPTED)
        self.assertTrue(snapshot.synthetic_acceptance)
        self.assertEqual(self.store.diagnostics()["live_successes"], 0)

    def test_r17_failed_intent_commit_prevents_dispatch(self):
        def fail(operation):
            if operation == "reserve":
                raise OSError("synthetic storage pressure")

        failing = SubmissionStateStore(
            Path(self.temporary.name) / "failing.sqlite3", before_commit=fail
        )
        with self.assertRaises(StorageCommitError):
            failing.reserve(self.scope, self.candidate)
        self.assertEqual(
            failing.duplicate_disposition(self.scope, self.candidate),
            DuplicateDisposition.NEW,
        )
        self.assertEqual(failing.diagnostics()["intents"], 0)

    def test_r17_capacity_pressure_preserves_required_records(self):
        reservation = self.dispatched()
        with self.assertRaises(StoragePressure):
            self.store.enforce_capacity(1)
        self.assertEqual(
            self.store.snapshot(reservation.intent_id).state,
            IntentState.DISPATCH_POSSIBLE,
        )


if __name__ == "__main__":
    unittest.main()
