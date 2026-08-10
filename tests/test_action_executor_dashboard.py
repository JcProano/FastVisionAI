import dataclasses
import threading
import unittest
from unittest.mock import patch

from src.engine.action_executor import ActionExecutor
from src.engine.decision_orchestrator import DecisionOrchestrator
from src.ui.contracts import ActionExecutorDTO, DecisionOrchestratorDTO
from src.ui.live_session import LiveFaceSession
from src.ui.main import build_action_executor
from src.ui.tk_app import action_executor_text


class ActionExecutorDashboardTests(unittest.TestCase):
    def test_dashboard_projection(self):
        dto = ActionExecutorDTO(
            "EXECUTION_DISABLED", True,
            ("SHOW_REGISTERED_POPUP", "LOG_DETECTION_EVENT"), (),
            ("SHOW_REGISTERED_POPUP", "LOG_DETECTION_EVENT"), (),
            ("automatic_execution_disabled",), False, "dev", "1",
        )
        text = action_executor_text(dto)
        self.assertEqual(text.state, "EXECUTION_DISABLED")
        self.assertEqual(text.executed, "—")
        self.assertEqual(text.automation, "Deshabilitada")

    def test_disabled_builder_and_dashboard(self):
        with patch("src.ui.main.ActionExecutor") as executor_type:
            result = build_action_executor({"action_executor": {"enabled": False}})
        self.assertIsNone(result); executor_type.assert_not_called()
        self.assertEqual(action_executor_text(None).state, "NOT_EVALUATED")

    def test_form_and_enrollment_reset(self):
        session = LiveFaceSession.__new__(LiveFaceSession)
        session._stability = None
        session._identification_policy = None
        session._decision_orchestrator = DecisionOrchestrator()
        session._action_executor = ActionExecutor()
        session._event_history_suspended = threading.Event()
        emitted = []
        session._event = emitted.append
        session.set_event_history_suspended(True)
        dto = next(item for item in emitted if isinstance(item, ActionExecutorDTO))
        self.assertEqual(dto.state, "NOT_EVALUATED")
        self.assertFalse(dto.evaluated)
        self.assertEqual(dto.requested_actions, ())
        self.assertEqual(dto.executed_actions, ())
        self.assertEqual(dto.skipped_actions, ())
        self.assertEqual(dto.failed_actions, ())

    def test_live_projection_is_execution_disabled_without_adapters(self):
        session = LiveFaceSession.__new__(LiveFaceSession)
        session._session_id = "session"
        session._action_executor = ActionExecutor()
        result = session._evaluate_action_executor(DecisionOrchestratorDTO(
            "ACTIONS_DISABLED", True, "person",
            ("SHOW_REGISTERED_POPUP", "LOG_DETECTION_EVENT"),
            ("SHOW_REGISTERED_POPUP", "LOG_DETECTION_EVENT"),
            ("automatic_actions_disabled",), False, "orchestrator", "1",
        ))
        self.assertEqual(result.state, "EXECUTION_DISABLED")
        self.assertEqual(result.requested_actions, (
            "SHOW_REGISTERED_POPUP", "LOG_DETECTION_EVENT",
        ))
        self.assertEqual(result.executed_actions, ())

    def test_dto_is_safe(self):
        forbidden = {
            "person_id", "embedding", "template", "image", "thumbnail", "array",
            "model", "similarity", "quality", "cedula", "name",
        }
        self.assertFalse({field.name for field in dataclasses.fields(ActionExecutorDTO)} &
                         forbidden)


if __name__ == "__main__":
    unittest.main()
