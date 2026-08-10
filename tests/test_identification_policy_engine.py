import unittest
from datetime import datetime, timezone

from src.engine.identification_policy import (
    IdentificationPolicy, IdentificationPolicyEngine, IdentificationPolicyInput,
    IdentificationPolicyState,
)


def policy_input(**changes):
    values = dict(
        person_id="person", recognition_state="NOT_EVALUATED", similarity=.8,
        stability_state="STABLE", stability_observations=5,
        stability_duration_seconds=2, quality_score=80,
        administrative_status="ACTIVE", face_count=1, run_id="run",
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    values.update(changes)
    return IdentificationPolicyInput(**values)


class IdentificationPolicyEngineTests(unittest.TestCase):
    def evaluate(self, policy=None, **changes):
        return IdentificationPolicyEngine(policy).evaluate(policy_input(**changes))

    def test_disabled_is_not_evaluated(self):
        result = self.evaluate(IdentificationPolicy(enabled=False))
        self.assertEqual(result.state, IdentificationPolicyState.POLICY_NOT_EVALUATED)
        self.assertFalse(result.evaluated)

    def test_exact_structural_precedence(self):
        no_face = self.evaluate(face_count=0, person_id=None,
                                recognition_state="INCOMPATIBLE")
        self.assertEqual(no_face.state, IdentificationPolicyState.NO_CANDIDATE)
        multiple = self.evaluate(face_count=2, person_id=None,
                                 recognition_state="INCOMPATIBLE")
        self.assertEqual(multiple.state, IdentificationPolicyState.AMBIGUOUS)
        incompatible = self.evaluate(recognition_state="INCOMPATIBLE", person_id=None)
        self.assertEqual(incompatible.state, IdentificationPolicyState.INCOMPATIBLE)
        ambiguous = self.evaluate(recognition_state="AMBIGUOUS", person_id=None)
        self.assertEqual(ambiguous.state, IdentificationPolicyState.AMBIGUOUS)
        missing = self.evaluate(person_id=None)
        self.assertEqual(missing.state, IdentificationPolicyState.NO_CANDIDATE)

    def test_only_active_person_passes_requirement(self):
        self.assertEqual(self.evaluate().state, IdentificationPolicyState.ELIGIBLE)
        for status in (
            "DISABLED", "PENDING_BIOMETRIC", "LEGACY_BIOMETRIC_ONLY", "NOT_FOUND", None,
        ):
            with self.subTest(status=status):
                result = self.evaluate(administrative_status=status)
                self.assertEqual(result.state, IdentificationPolicyState.PERSON_NOT_ACTIVE)

    def test_all_nonstable_states_fail(self):
        states = (
            "NO_OBSERVATION", "STABILIZING", "LOST", "CHANGED",
            "MULTIPLE_FACES", "INCOMPATIBLE",
        )
        for state in states:
            with self.subTest(state=state):
                self.assertEqual(
                    self.evaluate(stability_state=state).state,
                    IdentificationPolicyState.INSUFFICIENT_STABILITY,
                )

    def test_explicit_stability_minimums_are_independent(self):
        policy = IdentificationPolicy(
            minimum_stability_observations=6,
            minimum_stability_duration_seconds=3,
        )
        result = self.evaluate(policy)
        self.assertEqual(result.state, IdentificationPolicyState.INSUFFICIENT_STABILITY)
        self.assertEqual(result.reasons, (
            "stability_observations_insufficient", "stability_duration_insufficient",
        ))

    def test_optional_quality_rules(self):
        self.assertEqual(self.evaluate(quality_score=None).state,
                         IdentificationPolicyState.ELIGIBLE)
        policy = IdentificationPolicy(minimum_quality_score=70)
        self.assertEqual(self.evaluate(policy, quality_score=None).reasons,
                         ("quality_unavailable",))
        self.assertEqual(self.evaluate(policy, quality_score=69).reasons,
                         ("quality_below_policy_minimum",))
        self.assertEqual(self.evaluate(policy, quality_score=70).state,
                         IdentificationPolicyState.ELIGIBLE)

    def test_optional_similarity_is_administrative_only(self):
        self.assertEqual(self.evaluate(similarity=None).state,
                         IdentificationPolicyState.ELIGIBLE)
        policy = IdentificationPolicy(minimum_similarity=.7)
        self.assertEqual(self.evaluate(policy, similarity=None).reasons,
                         ("similarity_unavailable",))
        self.assertEqual(self.evaluate(policy, similarity=.69).reasons,
                         ("similarity_below_policy_minimum",))
        self.assertEqual(self.evaluate(policy, similarity=.7).state,
                         IdentificationPolicyState.ELIGIBLE)

    def test_multiple_reasons_have_stable_order_and_primary_state(self):
        policy = IdentificationPolicy(
            minimum_quality_score=90, minimum_similarity=.9,
            minimum_stability_observations=10,
        )
        result = self.evaluate(
            policy, administrative_status="DISABLED", stability_state="STABILIZING",
            quality_score=None, similarity=None,
        )
        self.assertEqual(result.state, IdentificationPolicyState.PERSON_NOT_ACTIVE)
        self.assertEqual(result.reasons, (
            "person_not_active", "observation_not_stable",
            "stability_observations_insufficient", "quality_unavailable",
            "similarity_unavailable",
        ))

    def test_unknown_states_degrade_safely(self):
        recognition = self.evaluate(recognition_state="FUTURE_STATE")
        self.assertEqual(recognition.state, IdentificationPolicyState.REJECTED_BY_POLICY)
        stability = self.evaluate(stability_state="FUTURE_STATE")
        self.assertEqual(stability.state, IdentificationPolicyState.INSUFFICIENT_STABILITY)

    def test_evaluation_is_deterministic_stateless_and_has_no_actions(self):
        policy = IdentificationPolicy(automatic_actions_enabled=False)
        engine = IdentificationPolicyEngine(policy)
        value = policy_input()
        first = engine.evaluate(value)
        self.assertEqual(first, engine.evaluate(value))
        self.assertTrue(first.eligible)
        self.assertEqual(engine.__slots__, ("policy",))


if __name__ == "__main__":
    unittest.main()
