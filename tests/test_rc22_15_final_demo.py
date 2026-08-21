from __future__ import annotations

import inspect
import time
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

import app as launcher
from src.camera.source_discovery import (
    CameraDiscoveryConfig, CameraSelectionController, CameraSourceDTO,
    CameraSourceType,
)
from src.engine.capture_quality import CapturePose
from src.ui.live_session import LiveFaceSession, requested_capture_pose
from src.ui.main import capture_mirror_from_presentation, main
from src.ui.mock_runtime import MockUIRuntimeAdapter


class StaticDiscovery:
    def __init__(self,sources,preferred=None):
        self.config=CameraDiscoveryConfig(source="auto",auto_discovery=True,
                                          preferred_source=preferred)
        self.sources=tuple(sources)
    def refresh(self): return self.sources


def camera(source_id,*,available,preferred=False):
    return CameraSourceDTO(source_id,CameraSourceType.NETWORK_HTTP,source_id,
                           available,preferred)


class RC2215FinalDemoTests(unittest.TestCase):
    def test_offline_preferred_falls_back_to_only_available_source(self):
        discovery=StaticDiscovery((
            camera("old",available=False,preferred=True),
            camera("online",available=True),
        ),preferred="old")
        result=CameraSelectionController(discovery).refresh()
        self.assertEqual(result.selected.source_id,"online")
        self.assertTrue(result.preferred_unavailable)

    def test_multiple_available_without_online_preference_requires_selector(self):
        discovery=StaticDiscovery((
            camera("old",available=False,preferred=True),
            camera("one",available=True),camera("two",available=True),
        ),preferred="old")
        result=CameraSelectionController(discovery).refresh()
        self.assertIsNone(result.selected)
        self.assertTrue(result.requires_selection)

    def test_online_preference_wins_even_when_multiple_are_available(self):
        discovery=StaticDiscovery((
            camera("preferred",available=True,preferred=True),
            camera("other",available=True),
        ),preferred="preferred")
        result=CameraSelectionController(discovery).refresh()
        self.assertEqual(result.selected.source_id,"preferred")

    def test_capture_mirror_ignores_disconnected_legacy_flag(self):
        settings={"camera":{"presentation":{"mirror_horizontal":False}},
                  "guided_capture":{"mirrored_source":True}}
        self.assertFalse(capture_mirror_from_presentation(settings))
        left=SimpleNamespace(requested_pose=CapturePose.SLIGHT_LEFT)
        right=SimpleNamespace(requested_pose=CapturePose.SLIGHT_RIGHT)
        self.assertIs(requested_capture_pose(left,False),CapturePose.SLIGHT_LEFT)
        self.assertIs(requested_capture_pose(right,False),CapturePose.SLIGHT_RIGHT)

    def test_pose_inverts_only_when_real_mirror_is_enabled(self):
        settings={"camera":{"presentation":{"mirror_horizontal":True}}}
        self.assertTrue(capture_mirror_from_presentation(settings))
        left=SimpleNamespace(requested_pose=CapturePose.SLIGHT_LEFT)
        right=SimpleNamespace(requested_pose=CapturePose.SLIGHT_RIGHT)
        self.assertIs(requested_capture_pose(left,True),CapturePose.SLIGHT_RIGHT)
        self.assertIs(requested_capture_pose(right,True),CapturePose.SLIGHT_LEFT)

    def test_enrollment_gate_uses_connected_active_camera_and_recent_frame(self):
        adapter=MockUIRuntimeAdapter()
        adapter.open()
        session=LiveFaceSession(adapter,Mock(),active_frame_max_age_seconds=3)
        session._thread=Mock(is_alive=Mock(return_value=True))
        session._last_frame_monotonic=time.monotonic()
        self.assertTrue(session.active_camera_ready())
        session._last_frame_monotonic=time.monotonic()-4
        self.assertFalse(session.active_camera_ready())
        session._last_frame_monotonic=time.monotonic()
        adapter.close()
        self.assertFalse(session.active_camera_ready())

    def test_python_app_default_is_integrated_jetson_ui(self):
        source=inspect.getsource(launcher.main)
        self.assertIn("config/local_face_validation.jetson.json",source)
        self.assertIn("from src.ui.main import main as ui_main",source)
        self.assertNotIn("192.168.",source)

    def test_startup_uses_selected_preference_before_opening_selector(self):
        source=inspect.getsource(main)
        finish=source[source.index("def finish_startup_camera_discovery"):
                      source.index("def start_network_camera_discovery")]
        self.assertIn("if result.selected is not None",finish)
        self.assertIn("use_camera(source)",finish)
        self.assertIn("open_camera_selection()",finish)


if __name__ == "__main__":
    unittest.main()
