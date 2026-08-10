import dataclasses
import threading
import unittest
from unittest.mock import patch

from src.engine.decision_orchestrator import DecisionOrchestrator
from src.engine.identification_policy import IdentificationPolicy, IdentificationPolicyEngine
from src.engine.stability import StabilityPolicy, StabilityTracker
from src.ui.contracts import DecisionOrchestratorDTO, MonitoringDTO, UIState
from src.ui.live_session import LiveFaceSession
from src.ui.main import build_decision_orchestrator
from src.ui.tk_app import decision_orchestrator_text


class DecisionOrchestratorDashboardTests(unittest.TestCase):
    def test_safe_dashboard_projection(self):
        dto = DecisionOrchestratorDTO(
            "ACTIONS_DISABLED", True, "person",
            ("SHOW_REGISTERED_POPUP", "LOG_DETECTION_EVENT"),
            ("SHOW_REGISTERED_POPUP", "LOG_DETECTION_EVENT"),
            ("automatic_actions_disabled",), False, "dev", "1",
        )
        text = decision_orchestrator_text(dto)
        self.assertEqual(text.state, "ACTIONS_DISABLED")
        self.assertIn("SHOW_REGISTERED_POPUP", text.proposals)
        self.assertEqual(text.automatic_actions, "Deshabilitadas")
        forbidden = {"embedding", "template", "image", "thumbnail", "model", "executed"}
        self.assertFalse({field.name for field in dataclasses.fields(dto)} & forbidden)

    def test_disabled_builder_does_not_construct_orchestrator(self):
        with patch("src.ui.main.DecisionOrchestrator") as orchestrator_type:
            result = build_decision_orchestrator({
                "decision_orchestrator": {"enabled": False},
            })
        self.assertIsNone(result)
        orchestrator_type.assert_not_called()
        self.assertEqual(decision_orchestrator_text(None).state, "NOT_EVALUATED")

    def test_live_session_emits_parallel_proposal_without_execution(self):
        session = LiveFaceSession.__new__(LiveFaceSession)
        session._stability = StabilityTracker(StabilityPolicy(
            minimum_observations=1, minimum_duration_seconds=0,
            policy_name="stability", policy_version="1",
        ))
        session._identification_policy = IdentificationPolicyEngine(IdentificationPolicy())
        session._decision_orchestrator = DecisionOrchestrator()
        session._session_id = "session"
        session._detection_events = None
        session._event_history_suspended = threading.Event()
        session._administrative_status_resolver = lambda _person: "ACTIVE"
        emitted = []
        session._event = emitted.append
        session._emit_monitoring(MonitoringDTO(
            UIState.MONITORING, "Candidato experimental", "Temporary", .8,
            "deshabilitada / NOT_EVALUATED", True, quality_score=80,
            recognition_state="NOT_EVALUATED", candidate_person_id="person",
        ))
        result = next(item for item in emitted if isinstance(item, DecisionOrchestratorDTO))
        self.assertEqual(result.state, "ACTIONS_DISABLED")
        self.assertIn("SHOW_REGISTERED_POPUP", result.proposed_actions)
        self.assertFalse(hasattr(result, "executed_actions"))

    def test_form_and_enrollment_reset_to_not_evaluated(self):
        session = LiveFaceSession.__new__(LiveFaceSession)
        session._stability = None
        session._identification_policy = None
        session._decision_orchestrator = DecisionOrchestrator()
        session._event_history_suspended = threading.Event()
        emitted = []
        session._event = emitted.append
        session.set_event_history_suspended(True)
        reset = next(item for item in emitted if isinstance(item, DecisionOrchestratorDTO))
        self.assertEqual(reset.state, "NOT_EVALUATED")
        self.assertEqual(reset.proposed_actions, ("NONE",))
        self.assertEqual(reset.blocked_actions, ())


if __name__ == "__main__":
    unittest.main()
