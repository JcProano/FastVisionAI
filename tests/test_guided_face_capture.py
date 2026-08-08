from __future__ import annotations

import tempfile
import threading
import unittest
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from src.camera.camera_types import ReadStatus
from src.camera.frame import Frame
from src.engine.alignment import AlignedFace, AlignmentQuality, AlignmentStatus
from src.engine.capture_quality import (
    FaceCaptureQualityEvaluator, GuidedCapturePlan, GuidedProfileDiagnosticCollector,
)
from src.engine.contracts.detection import BoundingBox, Detection
from src.engine.embedding.contracts import FaceEmbedding
from src.engine.face_quality import FaceQualityScorer, load_face_quality_profile
from src.validation.guided_face_capture import (
    GuidedCaptureSummary, GuidedOptions, load_guided_profile, persist_accepted, run_guided_loop,
    validate_persistence_options, validate_runtime_options, main as guided_main,
)


class GuidedFaceCaptureTests(unittest.TestCase):
    def test_development_profile_name_version_and_all_limits_load(self):
        profile = load_guided_profile(Path("config/guided_capture.dev.json"))
        self.assertEqual(profile.profile_name, "guided_capture_development")
        self.assertEqual(profile.profile_version, "1.0.0")
        self.assertGreater(profile.policy.min_blur_variance, 0)
        summary = GuidedCaptureSummary(
            profile.profile_name, profile.profile_version, 0, 0, 0, 0, 0, 0, 0, 0,
            {}, 0.0, 0.0, 0.0, (), "face_quality_development", "1.0.0", (), 0.0,
            False, False, "released", "released", "registered", "registered",
        )
        payload = asdict(summary)
        self.assertEqual(payload["profile_name"], "guided_capture_development")
        self.assertEqual(payload["profile_version"], "1.0.0")

    def test_headless_execution_requires_a_finite_limit(self):
        with self.assertRaises(ValueError):
            validate_runtime_options(GuidedOptions(None, None, True))
        validate_runtime_options(GuidedOptions(9, None, True))
        validate_runtime_options(GuidedOptions(9, 5.0, True))

    def test_consent_and_image_persistence_rules(self):
        with self.assertRaises(ValueError):
            validate_persistence_options(save_data=False, save_images=True,
                                         consent_confirmed=True)
        with self.assertRaises(Exception):
            validate_persistence_options(save_data=True, save_images=False,
                                         consent_confirmed=False)

    def test_rejected_samples_generate_no_artifacts(self):
        directory = tempfile.TemporaryDirectory(); self.addCleanup(directory.cleanup)
        output = Path(directory.name) / "guided"
        persist_accepted([], output, "temporary", "run", save_data=True,
                         save_images=False, consent_confirmed=True, overwrite=False)
        self.assertFalse(output.exists())

    def test_headless_mock_session_finishes_at_target_without_physical_camera(self):
        profile = load_guided_profile(Path("config/guided_capture.dev.json"))
        # Use the same configurable contract with permissive development limits.
        from dataclasses import replace
        policy = replace(profile.policy, min_blur_variance=0, min_contrast=0,
                         min_mean_illumination=0, max_mean_illumination=255,
                         max_near_duplicate_similarity=1.0)
        image = np.full((112, 112, 3), 128, dtype=np.uint8)
        frame = Frame(image, 1, "mock", datetime.now(timezone.utc), 1.0, 112, 112, 1)
        detection = Detection(BoundingBox(.25, .2, .75, .8, True), "face", .99, 0)
        inference = SimpleNamespace(detections=(detection,))
        aligned = AlignedFace(
            frame, image, detection.bounding_box,
            ((.35, .4), (.65, .4), (.5, .52), (.4, .68), (.6, .68)),
            np.eye(2, 3), np.eye(2, 3), 0, .99, "mock-run", AlignmentStatus.ALIGNED,
            AlignmentQuality.VALID, None, 1.0, .2, .2, 1.0,
        )
        vector = np.array([1, 0], dtype=np.float32); vector.setflags(write=False)
        embedding = FaceEmbedding(frame, "mock-run", 0, vector, 2, 1.0,
                                  AlignmentQuality.VALID, 1.0, "mock", "arc", "v1", "sha")

        class Camera:
            released = False
            def open(self): return True
            def read(self): return SimpleNamespace(status=ReadStatus.FRAME, frame=frame)
            def release(self): self.released = True

        camera = Camera()
        scorer = FaceQualityScorer(load_face_quality_profile(Path("config/face_quality.dev.json")))
        profile = load_guided_profile(Path("config/guided_capture.dev.json"))
        diagnostics = GuidedProfileDiagnosticCollector(
            profile.policy, profile.profile_name, profile.profile_version
        )
        captures, rejected, average, state = run_guided_loop(
            camera, lambda _frame, _run: inference, lambda _result: (aligned,),
            lambda _face: embedding, FaceCaptureQualityEvaluator(policy),
            GuidedCapturePlan(1), GuidedOptions(1, 1.0, True), threading.Event(), "mock-run",
            scorer, diagnostics.record,
        )
        camera.release()
        self.assertEqual(len(captures), 1)
        self.assertEqual(rejected, {})
        self.assertEqual(state, "connected")
        self.assertTrue(camera.released)
        self.assertTrue(captures[0].result.accepted)
        self.assertIsNotNone(captures[0].result.face_quality_score)
        self.assertEqual(average, captures[0].result.face_quality_score.total_score)
        report = diagnostics.report()
        self.assertEqual(report.frames_evaluated, 1)
        self.assertEqual(report.accepted_frames, 1)

    def test_diagnostic_mode_forbids_biometric_or_image_persistence(self):
        with patch("sys.argv", ["diagnose", "--temporary-id", "temporary",
                                "--save-data", "--consent-confirmed"]):
            with self.assertRaisesRegex(SystemExit, "does not permit"):
                guided_main(diagnostics_enabled=True)


if __name__ == "__main__": unittest.main()
