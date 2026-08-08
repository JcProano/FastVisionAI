import dataclasses
import unittest

from src.engine.stability import (
    StabilityObservation, StabilityPolicy, StabilityResult, StabilityState,
    StabilityValidationError,
)


class StabilityContractTests(unittest.TestCase):
    def test_defaults_are_temporal_and_do_not_define_identity_similarity(self):
        policy = StabilityPolicy()
        self.assertTrue(policy.enabled)
        self.assertEqual(policy.minimum_observations, 5)
        self.assertIsNone(policy.minimum_similarity)

    def test_invalid_policy_and_observation_are_rejected(self):
        for kwargs in (
            {"minimum_observations": 0}, {"minimum_duration_seconds": -1},
            {"maximum_gap_seconds": float("inf")}, {"minimum_similarity": 1.1},
            {"policy_name": ""},
        ):
            with self.assertRaises(StabilityValidationError):
                StabilityPolicy(**kwargs)
        with self.assertRaises(StabilityValidationError):
            StabilityObservation(0, None, "NOT_EVALUATED", float("nan"), 1, None, "run")

    def test_contracts_exclude_biometric_and_civil_payloads(self):
        forbidden = {
            "embedding", "embeddings", "template", "templates", "image", "thumbnail",
            "array", "model", "cedula", "address", "phone", "email", "display_name",
        }
        for contract in (StabilityObservation, StabilityResult):
            self.assertFalse({field.name for field in dataclasses.fields(contract)} & forbidden)

    def test_stable_state_is_named_only_as_temporal_state(self):
        self.assertEqual(StabilityState.STABLE.value, "STABLE")
        self.assertNotIn("MATCH", {state.value for state in StabilityState})


if __name__ == "__main__":
    unittest.main()
