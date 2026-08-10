import dataclasses
import unittest
from datetime import datetime, timezone

from src.engine.action_executor import (
    ActionExecutionContext, ActionExecutionInput, ActionExecutionResult,
    ActionExecutionState, ActionExecutorPolicy, ActionExecutorValidationError,
    ExecutableAction,
)


class ActionExecutorContractTests(unittest.TestCase):
    def test_safe_policy_defaults(self):
        policy = ActionExecutorPolicy()
        self.assertTrue(policy.enabled)
        self.assertFalse(policy.automatic_execution_enabled)
        self.assertFalse(policy.allow_attendance_execution)

    def test_attendance_cannot_be_enabled_in_this_phase(self):
        with self.assertRaises(ActionExecutorValidationError):
            ActionExecutorPolicy(allow_attendance_execution=True)

    def test_provenance_and_input_are_validated(self):
        with self.assertRaises(ActionExecutorValidationError):
            ActionExecutorPolicy(policy_name="")
        with self.assertRaises(ActionExecutorValidationError):
            ActionExecutionInput((), (), "", False, None, "run", "session",
                                 datetime.now(timezone.utc))

    def test_contracts_contain_no_biometric_or_civil_payload(self):
        forbidden = {
            "similarity", "quality", "cedula", "name", "address", "phone", "email",
            "embedding", "template", "image", "thumbnail", "array", "model",
        }
        for contract in (ActionExecutionInput, ActionExecutionContext, ActionExecutionResult):
            names = {field.name for field in dataclasses.fields(contract)}
            self.assertFalse(names & forbidden)

    def test_context_is_minimal(self):
        self.assertEqual(
            {field.name for field in dataclasses.fields(ActionExecutionContext)},
            {"action", "person_id", "run_id", "session_id", "orchestrator_state",
             "timestamp"},
        )
        context = ActionExecutionContext(
            ExecutableAction.LOG_DETECTION_EVENT, None, "run", "session", "STATE",
            datetime.now(timezone.utc),
        )
        self.assertEqual(context.action, ExecutableAction.LOG_DETECTION_EVENT)


if __name__ == "__main__":
    unittest.main()

