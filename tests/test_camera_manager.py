from __future__ import annotations

import threading
import unittest
from collections.abc import Iterable
from typing import Any

import numpy as np

from src.camera.camera_manager import CameraManager
from src.camera.camera_types import CameraConfig, CameraType, ReadStatus, ReconnectConfig


class FakeCapture:
    def __init__(self, opens: bool = True, reads: Iterable[tuple[bool, Any]] = ()) -> None:
        self.opens = opens
        self.reads = iter(reads)
        self.released = False
        self.opened_source: int | str | None = None
        self.properties: list[tuple[int, float]] = []

    def set(self, property_id: int, value: float) -> bool:
        self.properties.append((property_id, value))
        return True

    def open(self, source: int | str) -> bool:
        self.opened_source = source
        return self.opens

    def isOpened(self) -> bool:
        return self.opens and not self.released

    def read(self) -> tuple[bool, Any]:
        return next(self.reads, (False, None))

    def release(self) -> None:
        self.released = True


class CaptureSequence:
    def __init__(self, captures: Iterable[FakeCapture]) -> None:
        self.captures = iter(captures)
        self.calls = 0

    def __call__(self) -> FakeCapture:
        self.calls += 1
        return next(self.captures)


def camera_config(
    camera_type: CameraType,
    reconnect: ReconnectConfig | None = None,
) -> CameraConfig:
    source: int | str = 0 if camera_type is CameraType.USB else "rtsp://camera/live"
    if camera_type is CameraType.VIDEO_FILE:
        source = "data/video.mp4"
    return CameraConfig(
        name="test",
        camera_type=camera_type,
        source=source,
        reconnect=reconnect or ReconnectConfig(max_attempts=2, interval_seconds=0),
    )


class CameraManagerTests(unittest.TestCase):
    def test_reads_frame_and_releases_capture(self) -> None:
        image = np.zeros((480, 640, 3), dtype=np.uint8)
        capture = FakeCapture(reads=[(True, image)])
        manager = CameraManager(camera_config(CameraType.USB), capture_factory=lambda: capture)
        self.assertTrue(manager.open())
        result = manager.read()
        self.assertEqual(result.status, ReadStatus.FRAME)
        self.assertIsNotNone(result.frame)
        assert result.frame is not None
        self.assertIs(result.frame.image, image)
        self.assertEqual((result.frame.width, result.frame.height), (640, 480))
        self.assertEqual(result.frame.sequence_id, 1)
        manager.release()
        self.assertTrue(capture.released)

    def test_video_failure_is_normal_eof_without_reconnect(self) -> None:
        capture = FakeCapture(reads=[(False, None)])
        factory = CaptureSequence([capture])
        manager = CameraManager(camera_config(CameraType.VIDEO_FILE), capture_factory=factory)
        result = manager.read()
        self.assertEqual(result.status, ReadStatus.EOF)
        self.assertEqual(factory.calls, 1)

    def test_live_failure_reconnects_and_returns_frame(self) -> None:
        first = FakeCapture(reads=[(False, None)])
        image = np.zeros((240, 320, 3), dtype=np.uint8)
        second = FakeCapture(reads=[(True, image)])
        factory = CaptureSequence([first, second])
        manager = CameraManager(camera_config(CameraType.RTSP), capture_factory=factory)
        result = manager.read()
        self.assertEqual(result.status, ReadStatus.FRAME)
        self.assertIsNotNone(result.frame)
        assert result.frame is not None
        self.assertIs(result.frame.image, image)
        self.assertEqual(result.frame.connection_id, 2)
        self.assertEqual(factory.calls, 2)
        self.assertEqual(manager.reconnection_count, 1)

    def test_live_reconnect_stops_after_configured_attempts(self) -> None:
        reconnect = ReconnectConfig(max_attempts=2, interval_seconds=0)
        factory = CaptureSequence([FakeCapture(False), FakeCapture(False), FakeCapture(False)])
        manager = CameraManager(
            camera_config(CameraType.USB, reconnect),
            capture_factory=factory,
        )
        result = manager.read()
        self.assertEqual(result.status, ReadStatus.DISCONNECTED)
        self.assertEqual(factory.calls, 3)

    def test_cancellation_prevents_open(self) -> None:
        cancelled = threading.Event()
        cancelled.set()
        factory = CaptureSequence([FakeCapture()])
        manager = CameraManager(
            camera_config(CameraType.USB),
            cancel_event=cancelled,
            capture_factory=factory,
        )
        self.assertEqual(manager.read().status, ReadStatus.CANCELLED)
        self.assertEqual(factory.calls, 0)

    def test_disabled_reconnect_does_not_retry(self) -> None:
        reconnect = ReconnectConfig(enabled=False, max_attempts=4, interval_seconds=0)
        factory = CaptureSequence([FakeCapture(reads=[(False, None)])])
        manager = CameraManager(
            camera_config(CameraType.RTSP, reconnect),
            capture_factory=factory,
        )
        self.assertEqual(manager.read().status, ReadStatus.DISCONNECTED)
        self.assertEqual(factory.calls, 1)


if __name__ == "__main__":
    unittest.main()
