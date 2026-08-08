from __future__ import annotations

import time
import unittest

from src.engine.enrollment import EnrollmentPolicy, EnrollmentService
from src.engine.gallery import FaceGallery, FaceMatcher, MatchPolicy
from src.engine.recognition import RecognitionPolicy, RecognitionService
from src.ui.controller import LocalFaceUIController
from src.ui.enrollment_workflow import LocalEnrollmentWorkflow
from src.ui.live_session import LiveFaceSession
from src.ui.mock_runtime import MockUIRuntimeAdapter
from src.ui.recognition_session import ExperimentalRecognitionSession


def session():
    gallery = FaceGallery()
    matcher = FaceMatcher(policy=MatchPolicy(False, None))
    recognition = RecognitionService(gallery, matcher, RecognitionPolicy(top_k=matcher.top_k))
    enrollment = EnrollmentService(gallery, EnrollmentPolicy(1, 2))
    controller = LocalFaceUIController(
        ExperimentalRecognitionSession(recognition),
        LocalEnrollmentWorkflow(gallery, enrollment, 1),
    )
    return LiveFaceSession(MockUIRuntimeAdapter(delay=.002), controller)


class DashboardMetricsTests(unittest.TestCase):
    def test_metrics_reset_for_each_session_and_latency_is_unavailable(self):
        first = session()
        initial, _ = first.dashboard_telemetry()
        self.assertEqual(initial.frames_received, 0)
        self.assertIsNone(initial.inference_latency_ms)
        first.start(); time.sleep(.04)
        populated, quality = first.dashboard_telemetry()
        first.close()
        self.assertGreater(populated.frames_received, 0)
        self.assertEqual(populated.frames_received, populated.frames_processed)
        self.assertGreater(populated.visual_frames_dropped, 0)
        self.assertGreater(populated.faces_detected_total, 0)
        self.assertGreater(populated.embeddings_generated, 0)
        self.assertTrue(quality.metrics)
        second = session()
        reset, _ = second.dashboard_telemetry()
        self.assertEqual(reset.frames_received, 0)
        self.assertEqual(reset.visual_frames_dropped, 0)
        self.assertIsNone(reset.inference_latency_ms)
        second.close()


if __name__ == "__main__": unittest.main()
