from __future__ import annotations

import unittest
from datetime import datetime, timezone

import numpy as np

from src.camera.frame import Frame
from src.engine.alignment import AlignmentQuality
from src.engine.calibration.dataset import ConsentRequiredError, require_capture_consent
from src.engine.embedding.contracts import FaceEmbedding
from src.validation.capture_face_calibration import CapturePolicy, CaptureSampleSelector


class CaptureFaceCalibrationTests(unittest.TestCase):
    def embedding(self, vector, quality=AlignmentQuality.VALID):
        value = np.asarray(vector, dtype=np.float32); value /= np.linalg.norm(value)
        frame = Frame(np.zeros((2, 2, 3), dtype=np.uint8), 1, "mock", datetime.now(timezone.utc),
                      0, 2, 2, 1)
        return FaceEmbedding(frame, "run", 0, value, value.size, 1.0, quality, 1.0,
                             "mock", "arcface", "v1", "sha")

    def test_consent_required_only_when_artifacts_are_requested(self):
        require_capture_consent(save_data=False, save_images=False, consent_confirmed=False)
        for save_data, save_images in ((True, False), (False, True)):
            with self.assertRaises(ConsentRequiredError):
                require_capture_consent(save_data=save_data, save_images=save_images,
                                        consent_confirmed=False)

    def test_selector_enforces_time_quality_and_near_duplicate_filters(self):
        selector = CaptureSampleSelector(CapturePolicy(2, 4, 1.0, .999))
        self.assertTrue(selector.consider(self.embedding([1, 0]), 1.0))
        self.assertFalse(selector.consider(self.embedding([0, 1]), 1.5))
        self.assertFalse(selector.consider(self.embedding([1, 0]), 2.0))
        self.assertFalse(selector.consider(
            self.embedding([0, 1], AlignmentQuality.LOW_QUALITY), 2.0
        ))
        self.assertTrue(selector.consider(self.embedding([0, 1]), 2.0))


if __name__ == "__main__": unittest.main()
