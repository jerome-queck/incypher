import json
import unittest
from dataclasses import replace

from agent_ext.memory import (
    CandidateStatus,
    Dependencies,
    EvidenceCompleteness,
    EvidenceReference,
    EvidenceScope,
    ExecutionStatus,
    Experiment,
    Hypothesis,
    Interpretation,
    Observation,
    ProjectionFailure,
    ScopedMemory,
)


class ScopedMemoryTests(unittest.TestCase):
    def setUp(self):
        self.scope = EvidenceScope(
            "run-1", "solve", 7, "material-a", "attempt-1", "generation-1"
        )
        self.complete = EvidenceReference(
            "evidence:one", EvidenceCompleteness.COMPLETE, "tool:fixture", "bytes:0-20"
        )

    def observation(self, **changes):
        values = dict(
            observation_id="observation-1",
            scope=self.scope,
            evidence=self.complete,
            summary="gcd result was one",
            execution=ExecutionStatus.COMPLETED,
            sequence=1,
            interpretation=Interpretation.NEGATIVE,
            tested_conditions="the recorded pair of moduli",
        )
        values.update(changes)
        return Observation(**values)

    def experiment(self, **changes):
        values = dict(
            experiment_id="experiment-1",
            scope=self.scope,
            question="do the two moduli share a factor",
            dependencies=Dependencies(
                ("artifact:a", "artifact:b"),
                "gcd",
                "1",
                (("pair", "a,b"),),
                "exactly one recorded pair",
                ("python:3.12",),
                host_profile_revision="host-a",
            ),
            expected_outcomes=("nontrivial factor", "gcd is one"),
            admitted_budget={"seconds": 1},
            deterministic=True,
            generation_dependent=False,
            sequence=2,
            execution=ExecutionStatus.COMPLETED,
            interpretation=Interpretation.NEGATIVE,
            evidence_refs=("evidence:one",),
        )
        values.update(changes)
        return Experiment(**values)

    def test_r01_packet_preserves_fact_negative_test_and_unverified_suggestions(self):
        memory = ScopedMemory()
        memory.add_observation(self.observation())
        memory.add_experiment(self.experiment())
        memory.add_hypothesis(
            Hypothesis(
                "hypothesis-1",
                self.scope,
                "another weakness may remain",
                ("observation-1",),
                (),
                3,
            )
        )
        packet = memory.decision_packet(
            self.scope,
            objective="recover the challenge answer",
            request="choose one distinguishing experiment",
            restrictions=("use only the supplied fixture",),
            candidate_statuses=(
                CandidateStatus("opaque:abcdefgh", "qualified", "not_performed", "reserved"),
            ),
            next_experiment="inspect a different artifact property",
            maximum_bytes=5000,
        )
        self.assertLessEqual(packet.utf8_bytes, 5000)
        self.assertEqual(
            packet.packet["significant_failed_tests"][0]["interpretation"],
            "negative_within_tested_conditions",
        )
        self.assertEqual(
            packet.packet["hypotheses"][0]["status"], "unverified_suggestion"
        )
        self.assertEqual(
            packet.packet["next_experiment"]["status"], "unverified_suggestion"
        )
        self.assertTrue(packet.packet["uncertainty_preserved"])

    def test_r02_scope_changes_and_unknown_required_values_never_match(self):
        memory = ScopedMemory()
        memory.add_observation(self.observation(generation_dependent=True))
        for changed in (
            replace(self.scope, run_id="run-2"),
            replace(self.scope, phase="revisit"),
            replace(self.scope, challenge_id=8),
            replace(self.scope, material_ref="material-b"),
            replace(self.scope, instance_generation="generation-2"),
        ):
            packet = memory.decision_packet(
                changed,
                objective="fixture objective",
                request="fixture request",
                restrictions=("fixture restriction",),
            )
            self.assertEqual(packet.packet["observations"], [])
        with self.assertRaises(ValueError):
            replace(self.scope, run_id="")
        with self.assertRaises(ValueError):
            replace(self.scope, material_ref="")

    def test_r03_material_evidence_survives_host_profile_and_instance_changes(self):
        memory = ScopedMemory()
        memory.add_observation(self.observation(generation_dependent=False))
        memory.add_experiment(self.experiment())
        proposed = self.experiment(
            experiment_id="experiment-2",
            dependencies=replace(
                self.experiment().dependencies, host_profile_revision="host-b"
            ),
            execution=None,
            interpretation=Interpretation.UNRESOLVED,
        )
        self.assertTrue(memory.reusable_experiment(proposed).reusable)
        changed_generation = replace(self.scope, instance_generation="generation-2")
        packet = memory.decision_packet(
            changed_generation,
            objective="fixture objective",
            request="fixture request",
            restrictions=("fixture restriction",),
        )
        self.assertEqual(len(packet.packet["observations"]), 1)

    def test_r04_reuse_requires_equivalent_deterministic_work(self):
        memory = ScopedMemory()
        memory.add_experiment(self.experiment())
        equivalent = self.experiment(
            experiment_id="experiment-2",
            execution=None,
            interpretation=Interpretation.UNRESOLVED,
        )
        decision = memory.reusable_experiment(equivalent)
        self.assertTrue(decision.reusable)
        self.assertEqual(decision.evidence_refs, ("evidence:one",))
        changed = replace(
            equivalent,
            dependencies=replace(equivalent.dependencies, coverage="two recorded pairs"),
        )
        self.assertFalse(memory.reusable_experiment(changed).reusable)
        live = replace(
            equivalent,
            deterministic=False,
            live_trial_id="trial-2",
            repeat_reason="fresh live state",
        )
        self.assertFalse(memory.reusable_experiment(live).reusable)

    def test_r05_execution_limitations_cannot_be_negative_evidence(self):
        for status in (
            ExecutionStatus.TIMEOUT,
            ExecutionStatus.RESOURCE_LIMIT,
            ExecutionStatus.TOOL_UNAVAILABLE,
            ExecutionStatus.POLICY_BLOCKED,
            ExecutionStatus.MALFORMED_OUTPUT,
        ):
            with self.subTest(status=status):
                with self.assertRaises(ValueError):
                    self.observation(execution=status)
                unresolved = self.observation(
                    observation_id="observation-" + status.value,
                    execution=status,
                    interpretation=Interpretation.UNRESOLVED,
                    tested_conditions="",
                )
                self.assertEqual(unresolved.interpretation, Interpretation.UNRESOLVED)

    def test_r12_partial_capture_remains_explicit(self):
        memory = ScopedMemory()
        memory.add_observation(
            self.observation(
                evidence=replace(
                    self.complete, completeness=EvidenceCompleteness.PARTIAL
                ),
                interpretation=Interpretation.UNRESOLVED,
                tested_conditions="",
            )
        )
        packet = memory.decision_packet(
            self.scope,
            objective="fixture objective",
            request="fixture request",
            restrictions=("fixture restriction",),
        )
        self.assertEqual(
            packet.packet["observations"][0]["evidence"]["completeness"], "partial"
        )
        self.assertEqual(
            packet.packet["observations"][0]["interpretation"], "unresolved"
        )

    def test_r13_projection_rejects_private_material_and_derived_candidate_ids(self):
        memory = ScopedMemory()
        with self.assertRaises(ValueError):
            memory.decision_packet(
                self.scope,
                objective="INCYPHER{synthetic-secret}",
                request="fixture request",
                restrictions=("fixture restriction",),
            )
        with self.assertRaises(ValueError):
            CandidateStatus("a" * 64, "qualified", "passed", "reserved")
        with self.assertRaises(ValueError):
            memory.decision_packet(
                self.scope,
                objective="fixture objective",
                request="visit https://private.invalid/path",
                restrictions=("fixture restriction",),
            )

    def test_r13_utf8_byte_limit_and_overflow_are_explicit(self):
        memory = ScopedMemory()
        memory.add_observation(
            self.observation(summary="snowman ☃ and CJK 証拠" * 20)
        )
        packet = memory.decision_packet(
            self.scope,
            objective="fixture objective",
            request="fixture request",
            restrictions=("fixture restriction",),
            maximum_bytes=900,
        )
        encoded = json.dumps(
            packet.packet,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        self.assertEqual(packet.utf8_bytes, len(encoded))
        self.assertLessEqual(packet.utf8_bytes, 900)
        self.assertGreater(packet.packet["omissions"]["observations"], 0)
        with self.assertRaises(ProjectionFailure):
            memory.decision_packet(
                self.scope,
                objective="mandatory",
                request="mandatory",
                restrictions=("mandatory",),
                maximum_bytes=10,
            )


if __name__ == "__main__":
    unittest.main()
