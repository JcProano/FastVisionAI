from __future__ import annotations

import threading
import unittest

from src.camera.camera_types import CameraConfig, CameraType
from src.ui.live_session import LiveFaceSession


class CameraSwitchGuardTests(unittest.TestCase):
    def session(self):
        session = LiveFaceSession.__new__(LiveFaceSession)
        session._event_history_suspended = threading.Event()
        session._plan = None; session._photo_person_id = None
        session.controller = type("Controller", (), {
            "enrollment": type("Enrollment", (), {"active": False})()
        })()
        session._command = lambda _command: True
        return session

    def test_form_and_enrollment_block_camera_switch(self):
        session = self.session(); cfg = CameraConfig("safe", CameraType.USB, 0)
        session._event_history_suspended.set()
        self.assertFalse(session.camera_switch_allowed); self.assertFalse(session.switch_camera(cfg))
        session._event_history_suspended.clear(); session.controller.enrollment.active = True
        self.assertFalse(session.camera_switch_allowed); self.assertFalse(session.switch_camera(cfg))

    def test_photo_capture_blocks_camera_switch(self):
        session = self.session(); session._photo_person_id = "safe-person-id"
        self.assertFalse(session.camera_switch_allowed)
        self.assertFalse(session.switch_camera(CameraConfig("safe", CameraType.USB, 0)))

    def test_monitoring_allows_camera_switch(self):
        session = self.session()
        self.assertTrue(session.camera_switch_allowed)
        self.assertTrue(session.switch_camera(CameraConfig("safe", CameraType.USB, 2)))


if __name__ == "__main__":
    unittest.main()
