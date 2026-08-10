import dataclasses
import unittest
from datetime import datetime, timezone

from src.engine.decision_orchestrator import (
    DecisionOrchestratorInput, DecisionOrchestratorPolicy,
    DecisionOrchestratorResult, DecisionOrchestratorValidationError,
    DecisionState, ProposedAction,
)


class DecisionOrchestratorContractTests(unittest.TestCase):
    def test_safe_defaults_disable_actions_and_attendance(self):
        policy = DecisionOrchestratorPolicy()
        self.assertTrue(policy.enabled)
        self.assertFalse(policy.automatic_actions_enabled)
        self.assertFalse(policy.allow_attendance_proposal)

    def test_policy_provenance_and_input_are_validated(self):
        with self.assertRaises(DecisionOrchestratorValidationError):
            DecisionOrchestratorPolicy(policy_name="")
        with self.assertRaises(DecisionOrchestratorValidationError):
            DecisionOrchestratorInput(
                -1, None, "NOT_EVALUATED", None, "NO_OBSERVATION",
                "NO_CANDIDATE", False, None, None, "run", "session",
                datetime.now(timezone.utc),
            )

    def test_none_cannot_be_mixed_and_executed_actions_do_not_exist(self):
        with self.assertRaises(DecisionOrchestratorValidationError):
            DecisionOrchestratorResult(
                DecisionState.OBSERVATION_ONLY, True, None,
                (ProposedAction.NONE, ProposedAction.LOG_DETECTION_EVENT), (), (),
                False, "test", "1", datetime.now(timezone.utc),
            )
        fields = {field.name for field in dataclasses.fields(DecisionOrchestratorResult)}
        self.assertNotIn("executed_actions", fields)

    def test_contracts_exclude_pii_biometrics_and_dependencies(self):
        forbidden = {
            "display_name", "cedula", "address", "phone", "email", "embedding",
            "template", "image", "thumbnail", "array", "model", "repository",
            "executed_actions",
        }
        for contract in (DecisionOrchestratorInput, DecisionOrchestratorResult):
            self.assertFalse({field.name for field in dataclasses.fields(contract)} & forbidden)


if __name__ == "__main__":
    unittest.main()
