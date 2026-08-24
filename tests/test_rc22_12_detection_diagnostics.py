"""RC22.12 diagnostic instrumentation must remain behavior-neutral."""

from __future__ import annotations

import logging
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np

from src.camera.frame import Frame
from src.engine.capture_quality import CapturePose, GuidedCaptureState
from src.engine.contracts.detection import BoundingBox, Detection
from src.engine.contracts.metrics import InferenceMetrics
from src.ui.live_session import LiveFaceSession
from src.ui.mock_runtime import MockUIRuntimeAdapter
from src.ui.runtime_adapter import _log_detection_diagnostic


class RC2212DetectionDiagnosticTests(unittest.TestCase):
    def test_diagnostic_log_does_not_mutate_detections(self):
        frame = Frame(
            np.zeros((100, 200, 3), np.uint8), 77, "safe-camera",
            datetime.now(timezone.utc), 12.5, 200, 100, 1,
        )
        detections = (
            Detection(BoundingBox(20, 10, 100, 80, False), "face", .91),
            Detection(BoundingBox(.55, .1, .95, .8, True), "face", .72),
        )
        inference = SimpleNamespace(
            detections=detections, metrics=InferenceMetrics(8.25, 2),
        )

        with self.assertLogs("src.ui.runtime_adapter", logging.DEBUG) as captured:
            _log_detection_diagnostic(inference, frame, "diagnostic-run")

        self.assertIs(inference.detections, detections)
        self.assertEqual(len(inference.detections), 2)
        message = captured.output[0]
        self.assertIn("face_detection_diag", message)
        self.assertIn("frame_id=77", message)
        self.assertIn("detection_count=2", message)
        self.assertIn("'index': 0", message)
        self.assertIn("'confidence': 0.91", message)
        self.assertIn("'bbox': (0.1, 0.1, 0.5, 0.8)", message)

    def test_multiple_face_diagnostic_preserves_state_and_sample_count(self):
        adapter = MockUIRuntimeAdapter(multiple_at={1}, delay=0)
        step = adapter.process(CapturePose.FRONTAL)
        session = LiveFaceSession.__new__(LiveFaceSession)
        session._plan = SimpleNamespace(
            accepted_count=2, target_samples=5,
            current=SimpleNamespace(
                requested_pose=CapturePose.SLIGHT_RIGHT, instruction="Gire a la derecha",
            ),
            completed=False,
        )
        session._enrollment_stability = SimpleNamespace(reset=lambda: None)
        session.mirrored_source = False
        session.controller = SimpleNamespace(state=SimpleNamespace(value="enrolling"))
        events = []
        session._event = events.append

        with self.assertLogs("src.ui.live_session", logging.DEBUG) as captured:
            session._enrollment_step(
                step.guided, frame_id=step.frame_id, detection_count=step.face_count,
            )

        self.assertIs(step.guided.primary_state, GuidedCaptureState.MULTIPLE_FACES)
        self.assertEqual(session._plan.accepted_count, 2)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].current_reasons, ("multiple_faces",))
        self.assertEqual(events[0].frame_id, step.visual.sequence_id)
        self.assertIn("enrollment_multiple_faces", captured.output[0])
        self.assertIn("detection_count=2", captured.output[0])


if __name__ == "__main__":
    unittest.main()
