import dataclasses
import threading
import unittest
from unittest.mock import patch

from src.engine.identification_policy import IdentificationPolicy, IdentificationPolicyEngine
from src.engine.stability import StabilityPolicy, StabilityTracker
from src.ui.contracts import IdentificationPolicyDTO, MonitoringDTO, UIState
from src.ui.live_session import LiveFaceSession
from src.ui.main import build_identification_policy_engine
from src.ui.tk_app import identification_policy_text


class IdentificationPolicyDashboardTests(unittest.TestCase):
    def test_safe_dto_and_informative_text(self):
        dto = IdentificationPolicyDTO(
            "INSUFFICIENT_STABILITY", True, False, "person",
            ("observation_not_stable",), .8, 80, "STABILIZING", "ACTIVE",
            "dev", "1", False,
        )
        text = identification_policy_text(dto)
        self.assertEqual(text.state, "INSUFFICIENT_STABILITY")
        self.assertEqual(text.evaluated, "Sí")
        self.assertEqual(text.automatic_actions, "Deshabilitadas")
        forbidden = {"embedding", "template", "image", "thumbnail", "model", "cedula"}
        self.assertFalse({field.name for field in dataclasses.fields(dto)} & forbidden)

    def test_disabled_builder_is_nonfatal_and_does_not_construct_engine(self):
        with patch("src.ui.main.IdentificationPolicyEngine") as engine_type:
            result = build_identification_policy_engine({
                "identification_policy": {"enabled": False},
            })
        self.assertIsNone(result)
        engine_type.assert_not_called()
        self.assertEqual(identification_policy_text(None).state, "POLICY_NOT_EVALUATED")

    def test_live_session_parallel_projection_and_resolver_failure(self):
        tracker = StabilityTracker(StabilityPolicy(
            minimum_observations=1, minimum_duration_seconds=0,
            policy_name="stability", policy_version="1",
        ))
        engine = IdentificationPolicyEngine(IdentificationPolicy())
        session = LiveFaceSession.__new__(LiveFaceSession)
        session._stability = tracker
        session._identification_policy = engine
        session._session_id = "session"
        session._detection_events = None
        session._event_history_suspended = threading.Event()
        session._administrative_status_resolver = lambda _person: "ACTIVE"
        emitted = []
        session._event = emitted.append
        monitoring = MonitoringDTO(
            UIState.MONITORING, "Candidato experimental", "Temporary", .8,
            "deshabilitada / NOT_EVALUATED", True, quality_score=80,
            recognition_state="NOT_EVALUATED", candidate_person_id="person",
        )
        session._emit_monitoring(monitoring)
        policy_dto = next(item for item in emitted if isinstance(item, IdentificationPolicyDTO))
        self.assertEqual(policy_dto.state, "ELIGIBLE")
        self.assertFalse(policy_dto.automatic_actions_enabled)

        session._administrative_status_resolver = lambda _person: (_ for _ in ()).throw(
            RuntimeError("private")
        )
        emitted.clear()
        with self.assertLogs("src.ui.live_session", level="WARNING") as logs:
            session._emit_monitoring(monitoring)
        failed = next(item for item in emitted if isinstance(item, IdentificationPolicyDTO))
        self.assertEqual(failed.state, "PERSON_NOT_ACTIVE")
        self.assertNotIn("private", " ".join(logs.output).lower())

    def test_enrollment_reset_projects_not_evaluated(self):
        session = LiveFaceSession.__new__(LiveFaceSession)
        session._stability = None
        session._identification_policy = IdentificationPolicyEngine(IdentificationPolicy())
        session._event_history_suspended = threading.Event()
        emitted = []
        session._event = emitted.append
        session.set_event_history_suspended(True)
        self.assertEqual(emitted[-1].state, "POLICY_NOT_EVALUATED")
        self.assertFalse(emitted[-1].evaluated)


if __name__ == "__main__":
    unittest.main()
