import dataclasses
import unittest
from datetime import datetime, timezone

from src.engine.identification_policy import (
    IdentificationPolicy, IdentificationPolicyInput, IdentificationPolicyResult,
    IdentificationPolicyState, IdentificationPolicyValidationError,
)


class IdentificationPolicyContractTests(unittest.TestCase):
    def test_safe_defaults_have_no_thresholds_or_actions(self):
        policy = IdentificationPolicy()
        self.assertTrue(policy.enabled)
        self.assertFalse(policy.automatic_actions_enabled)
        self.assertIsNone(policy.minimum_quality_score)
        self.assertIsNone(policy.minimum_similarity)

    def test_invalid_policy_values_are_rejected(self):
        cases = (
            {"minimum_quality_score": -1}, {"minimum_quality_score": 101},
            {"minimum_similarity": -1.1}, {"minimum_similarity": float("nan")},
            {"minimum_stability_observations": 0},
            {"minimum_stability_duration_seconds": -1}, {"policy_name": ""},
        )
        for values in cases:
            with self.subTest(values=values), self.assertRaises(
                IdentificationPolicyValidationError
            ):
                IdentificationPolicy(**values)

    def test_input_validation_and_administrative_statuses(self):
        for status in (
            "ACTIVE", "DISABLED", "PENDING_BIOMETRIC", "LEGACY_BIOMETRIC_ONLY",
            "NOT_FOUND", None,
        ):
            IdentificationPolicyInput(
                "person", "NOT_EVALUATED", .5, "STABLE", 5, 1.5, 80,
                status, 1, "run", datetime.now(timezone.utc),
            )
        with self.assertRaises(IdentificationPolicyValidationError):
            IdentificationPolicyInput(
                "person", "NOT_EVALUATED", .5, "STABLE", 5, 1.5, 80,
                "UNSAFE", 1, "run", datetime.now(timezone.utc),
            )

    def test_public_contracts_exclude_pii_and_biometrics(self):
        forbidden = {
            "display_name", "cedula", "address", "phone", "email", "notes",
            "embedding", "embeddings", "template", "templates", "image", "thumbnail",
            "array", "model", "path",
        }
        for contract in (IdentificationPolicyInput, IdentificationPolicyResult):
            self.assertFalse({field.name for field in dataclasses.fields(contract)} & forbidden)
        self.assertNotIn("MATCH", {state.value for state in IdentificationPolicyState})


if __name__ == "__main__":
    unittest.main()
