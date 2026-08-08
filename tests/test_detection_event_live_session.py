import queue
import tempfile
import threading
import unittest
from pathlib import Path

from src.core.detection_events import DetectionEventRepository, DetectionEventService
from src.ui.contracts import MonitoringDTO, UIState
from src.ui.live_session import LiveFaceSession


class DetectionEventLiveSessionTests(unittest.TestCase):
    def session(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        repository = DetectionEventRepository(Path(temporary.name) / "events.db")
        repository.initialize(); service = DetectionEventService(repository, registered_cooldown_seconds=0,
                                                                  unregistered_cooldown_seconds=0)
        session = LiveFaceSession.__new__(LiveFaceSession)
        session._detection_events = service; session._event_history_suspended = threading.Event()
        session._camera_id = "mock"; session._session_id = "session"
        session._administrative_status_resolver = None
        session.event_queue = queue.Queue(maxsize=20)
        return repository, session

    def test_no_face_not_persisted_and_supported_observations_are(self):
        repository, session = self.session()
        session._emit_monitoring(MonitoringDTO(
            UIState.NO_FACE, "none", None, None, "NOT_EVALUATED", True,
        ))
        self.assertEqual(repository.count(), 0)
        session._emit_monitoring(MonitoringDTO(
            UIState.MULTIPLE_FACES, "multiple", None, None, "NOT_EVALUATED", True,
        ))
        session._emit_monitoring(MonitoringDTO(
            UIState.MONITORING, "candidate", "Temporary", .8, "NOT_EVALUATED", True,
            quality_score=80, recognition_state="NOT_EVALUATED", candidate_person_id="person-1",
        ))
        self.assertEqual(repository.count(), 2)
        self.assertTrue(all(item.recognition_state == "NOT_EVALUATED" for item in repository.list()))

    def test_form_enrollment_and_rollback_suspension_until_monitoring(self):
        repository, session = self.session()
        session.set_event_history_suspended(True)
        event = MonitoringDTO(UIState.MONITORING, "unknown", None, None,
                              "NOT_EVALUATED", True, recognition_state="NO_GALLERY")
        session._emit_monitoring(event); self.assertEqual(repository.count(), 0)
        session.set_event_history_suspended(False)
        session._emit_monitoring(event); self.assertEqual(repository.count(), 1)


if __name__ == "__main__": unittest.main()
