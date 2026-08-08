import dataclasses
import unittest
from unittest.mock import patch

from src.engine.stability import StabilityPolicy, StabilityTracker
from src.ui.contracts import StabilityDTO
from src.ui.main import build_stability_tracker
from src.ui.live_session import LiveFaceSession
from src.ui.contracts import MonitoringDTO, StabilityDTO, UIState
from src.ui.tk_app import stability_text


class StabilityDashboardTests(unittest.TestCase):
    def test_safe_projection_and_informative_text(self):
        dto = StabilityDTO("STABILIZING", "person", 3, 5, .8, 1.5, .7, .7421, "stabilizing")
        text = stability_text(dto)
        self.assertEqual(text.state, "STABILIZING")
        self.assertEqual(text.observations, "3/5")
        self.assertEqual(text.duration, "0.8 / 1.5 s")
        self.assertEqual(text.average_similarity, "0.7421")
        forbidden = {"embedding", "template", "image", "thumbnail", "array", "model"}
        self.assertFalse({field.name for field in dataclasses.fields(dto)} & forbidden)

    def test_missing_and_disabled_are_nonfatal(self):
        self.assertEqual(stability_text(None).state, "N/D")
        with patch("src.ui.main.StabilityTracker") as tracker_type:
            result = build_stability_tracker({"stability": {"enabled": False}})
        self.assertIsNone(result)
        tracker_type.assert_not_called()

    def test_configuration_builds_explicit_policy(self):
        tracker = build_stability_tracker({"stability": {
            "enabled": True, "minimum_observations": 7,
            "minimum_duration_seconds": 2, "maximum_gap_seconds": .5,
            "minimum_similarity": None, "reset_on_multiple_faces": True,
            "reset_on_candidate_change": True, "policy_name": "dev", "policy_version": "2",
        }})
        self.assertIsInstance(tracker, StabilityTracker)
        self.assertEqual(tracker.policy, StabilityPolicy(
            True, 7, 2, .5, None, True, True, "dev", "2",
        ))

    def test_live_session_projects_safe_state_and_resets_for_enrollment(self):
        tracker = StabilityTracker(StabilityPolicy(
            minimum_observations=2, minimum_duration_seconds=0,
            policy_name="test", policy_version="1",
        ))
        session = LiveFaceSession.__new__(LiveFaceSession)
        session._stability = tracker
        session._session_id = "session"
        session._detection_events = None
        session._event_history_suspended = __import__("threading").Event()
        emitted = []
        session._event = emitted.append
        session._emit_monitoring(MonitoringDTO(
            UIState.MONITORING, "Candidato experimental", "Temporary", .8,
            "deshabilitada / NOT_EVALUATED", True,
            recognition_state="NOT_EVALUATED", candidate_person_id="person",
        ))
        self.assertIsInstance(emitted[0], StabilityDTO)
        self.assertEqual(emitted[0].observations_count, 1)
        session.set_event_history_suspended(True)
        self.assertEqual(tracker.snapshot().observations_count, 0)
        self.assertEqual(emitted[-1].state, "NO_OBSERVATION")


if __name__ == "__main__":
    unittest.main()
