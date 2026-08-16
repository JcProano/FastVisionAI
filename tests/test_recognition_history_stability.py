import unittest
from datetime import datetime, timezone

from src.engine.decision_orchestrator import (
    DecisionOrchestrator, DecisionOrchestratorInput, DecisionOrchestratorPolicy,
)
from src.ui.detection_history.tk_window import local_event_parts
from src.ui.live_session import _safe_camera_reference


class RecognitionHistoryStabilityTests(unittest.TestCase):
    def _evaluate(self, stability):
        engine = DecisionOrchestrator(DecisionOrchestratorPolicy(
            automatic_actions_enabled=True, allow_detection_event_proposal=True,
            allow_registered_popup_proposal=False,
        ))
        return engine.evaluate(DecisionOrchestratorInput(
            1, "person", "NOT_EVALUATED", .92, stability, "ELIGIBLE", True,
            "ACTIVE", 82.0, "run", "session", datetime.now(timezone.utc),
        ))

    def test_registered_event_requires_stability_when_tracker_is_active(self):
        self.assertNotIn("LOG_DETECTION_EVENT", tuple(
            item.value for item in self._evaluate("STABILIZING").proposed_actions))
        self.assertIn("LOG_DETECTION_EVENT", tuple(
            item.value for item in self._evaluate("STABLE").proposed_actions))

    def test_camera_credentials_are_redacted(self):
        safe = _safe_camera_reference("rtsp://user:secret@camera.local/live", "camera-1")
        self.assertNotIn("secret", safe)
        self.assertIn("camera.local", safe)

    def test_utc_timestamp_is_presented_in_guayaquil(self):
        date, hour = local_event_parts(datetime(2026, 1, 10, 15, 30, tzinfo=timezone.utc))
        self.assertEqual((date, hour), ("2026-01-10", "10:30:00"))


if __name__ == "__main__": unittest.main()
