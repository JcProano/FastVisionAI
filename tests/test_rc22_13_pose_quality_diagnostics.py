"""RC22.13 behavior-neutral pose and quality diagnostic coverage."""

from __future__ import annotations

import logging
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from src.camera.frame import Frame
from src.engine.capture_quality import CapturePose, FaceCaptureQualityEvaluator
from src.engine.contracts.detection import BoundingBox, Detection
from src.engine.contracts.metrics import InferenceMetrics
from src.ui.live_session import requested_capture_pose
from src.ui.runtime_adapter import _log_enrollment_quality_diagnostic
from src.ui.tk_app import _enrollment_checklist
from src.validation.guided_face_capture import load_guided_profile


class RC2213PoseQualityDiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = load_guided_profile(Path("config/guided_capture.dev.json")).policy

    @staticmethod
    def landmarks(nose_x):
        return ((.35, .4), (.65, .4), (nose_x, .52), (.4, .68), (.6, .68))

    def test_raw_landmark_sign_and_evaluator_mirror_are_explicit(self):
        evaluator = FaceCaptureQualityEvaluator(self.policy)
        self.assertIs(evaluator._estimate_pose(self.landmarks(.44))[0], CapturePose.SLIGHT_LEFT)
        self.assertIs(evaluator._estimate_pose(self.landmarks(.50))[0], CapturePose.FRONTAL)
        self.assertIs(evaluator._estimate_pose(self.landmarks(.56))[0], CapturePose.SLIGHT_RIGHT)

        mirrored = FaceCaptureQualityEvaluator(replace(self.policy, mirrored_source=True))
        self.assertIs(mirrored._estimate_pose(self.landmarks(.44))[0], CapturePose.SLIGHT_RIGHT)
        self.assertIs(mirrored._estimate_pose(self.landmarks(.56))[0], CapturePose.SLIGHT_LEFT)

    def test_session_mirror_flips_expected_pose_without_changing_instruction(self):
        step = SimpleNamespace(
            requested_pose=CapturePose.SLIGHT_RIGHT,
            instruction="Gire ligeramente el rostro hacia la derecha",
        )
        self.assertIs(requested_capture_pose(step, False), CapturePose.SLIGHT_RIGHT)
        self.assertIs(requested_capture_pose(step, True), CapturePose.SLIGHT_LEFT)
        self.assertIn("derecha", step.instruction)

    def test_quality_log_reads_existing_values_without_mutating_result(self):
        frame = Frame(
            np.zeros((100, 200, 3), np.uint8), 91, "safe-camera",
            datetime.now(timezone.utc), 10.0, 200, 100, 1,
        )
        detection = Detection(BoundingBox(.2, .1, .6, .7, True), "face", .70)
        inference = SimpleNamespace(
            detections=(detection,), metrics=InferenceMetrics(5.0, 1),
        )
        metrics = SimpleNamespace(
            relative_face_size=.24, normalized_interocular_distance=.09,
            eye_nose_yaw_ratio=.20, mouth_nose_yaw_ratio=.19,
        )
        score = SimpleNamespace(total_score=40.2, quality_band=SimpleNamespace(value="poor"))
        guided = SimpleNamespace(
            reasons=(SimpleNamespace(value="low_detection_confidence"),
                     SimpleNamespace(value="pose_not_requested")),
            quality_metrics=metrics, face_quality_score=score,
            requested_pose=CapturePose.SLIGHT_LEFT,
            estimated_pose=CapturePose.SLIGHT_RIGHT,
        )

        with self.assertLogs("src.ui.runtime_adapter", logging.DEBUG) as captured:
            _log_enrollment_quality_diagnostic(inference, frame, guided, self.policy)

        self.assertEqual(inference.detections, (detection,))
        message = captured.output[0]
        self.assertIn("enrollment_quality_diag frame_id=91", message)
        self.assertIn("detection_confidence=0.700000", message)
        self.assertIn("min_detection_confidence=0.750000", message)
        self.assertIn("expected_pose=slight_left detected_pose=slight_right", message)
        self.assertIn("quality_score=40.200000", message)

    def test_two_of_five_renders_two_completed_sample_labels(self):
        checklist = _enrollment_checklist(2, 5).splitlines()
        self.assertEqual(checklist[0], "✓ Frontal")
        self.assertEqual(checklist[1], "✓ Ligero giro izquierda")
        self.assertTrue(all(line.startswith("○") for line in checklist[2:]))


if __name__ == "__main__":
    unittest.main()
