import unittest

from agent_ext.scheduler import (
    Challenge,
    SchedulingRecord,
    Scope,
    SelectionPolicy,
    select_challenge,
)


def record(name, *, attempts=0, bypasses=0, progress=0, eligible=True, **metadata):
    return SchedulingRecord(
        Challenge(Scope(name, "material-1"), "authority-1", **metadata),
        eligible,
        attempts,
        bypasses,
        progress,
    )


class SchedulerTests(unittest.TestCase):
    def test_empty_or_all_blocked(self):
        self.assertIsNone(select_challenge([]))
        self.assertIsNone(select_challenge([record("a", eligible=False)]))

    def test_missing_category_points_and_costs_have_stable_fallback(self):
        for policy in SelectionPolicy:
            with self.subTest(policy=policy):
                items = [record("c"), record("a"), record("b")]
                self.assertEqual(
                    select_challenge(items, policy=policy).challenge.scope.challenge_id,
                    "a",
                )
                self.assertEqual(
                    select_challenge(reversed(items), policy=policy), items[1]
                )

    def test_initial_coverage_precedes_productive_retry(self):
        chosen = select_challenge([record("a", attempts=1, progress=10), record("b")])
        self.assertEqual(chosen.challenge.scope.challenge_id, "b")

    def test_recent_evidence_then_measured_setup_cost(self):
        items = [
            record("a", attempts=1, progress=1, setup_seconds=0),
            record("b", attempts=1, progress=2, setup_seconds=5),
            record("c", attempts=1, progress=2, setup_seconds=1),
        ]
        self.assertEqual(select_challenge(items).challenge.scope.challenge_id, "c")

    def test_cheap_initial_triage_is_preferred(self):
        items = [record("a", setup_seconds=9), record("b", setup_seconds=1)]
        self.assertEqual(select_challenge(items).challenge.scope.challenge_id, "b")

    def test_aged_eligible_work_beats_new_arrivals(self):
        chosen = select_challenge([record("a", attempts=2, bypasses=3), record("b")])
        self.assertEqual(chosen.challenge.scope.challenge_id, "a")

    def test_aging_never_revives_blocked_work(self):
        chosen = select_challenge(
            [record("a", bypasses=1000, eligible=False), record("b")]
        )
        self.assertEqual(chosen.challenge.scope.challenge_id, "b")

    def test_coverage_baseline_ignores_unmeasured_heuristics(self):
        chosen = select_challenge(
            [record("a", attempts=1), record("b", attempts=1, progress=99)],
            policy=SelectionPolicy.COVERAGE,
        )
        self.assertEqual(chosen.challenge.scope.challenge_id, "a")

    def test_optional_benefit_cost_uses_only_complete_measurements(self):
        items = [
            record("a", points=1000),
            record("b", points=10, setup_seconds=1, remaining_seconds=1),
            record("c", points=100, setup_seconds=20, remaining_seconds=20),
        ]
        self.assertEqual(
            select_challenge(
                items, policy=SelectionPolicy.BENEFIT_COST
            ).challenge.scope.challenge_id,
            "b",
        )

    def test_category_is_metadata_not_an_assumed_difficulty(self):
        self.assertEqual(
            select_challenge(
                [record("b", category="misc"), record("a", category="pwn")]
            ).challenge.scope.challenge_id,
            "a",
        )

    def test_duplicate_scopes_are_rejected(self):
        with self.assertRaises(ValueError):
            select_challenge([record("a"), record("a")])

    def test_invalid_costs_and_identifiers_are_rejected(self):
        for value in (True, -1, float("nan"), float("inf"), "5"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                record("a", points=value)
        with self.assertRaises(ValueError):
            record("a", remaining_seconds=0)
        with self.assertRaises(ValueError):
            Scope("bad\nreference", "material")


if __name__ == "__main__":
    unittest.main()
