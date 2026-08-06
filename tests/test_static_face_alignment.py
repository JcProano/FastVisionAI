from __future__ import annotations

import unittest

import numpy as np

from src.camera.frame import Frame
from src.engine.alignment import AlignmentQuality, AlignmentStatus, AlignedFace
from src.engine.contracts.detection import BoundingBox, Detection, InferenceResult
from src.engine.contracts.metrics import InferenceMetrics
from src.validation.static_face_alignment import draw_diagnostic


class StaticFaceAlignmentTests(unittest.TestCase):
    def test_diagnostic_preserves_dimensions(self):
        image = np.zeros((100, 100, 3), dtype=np.uint8)
        frame = Frame.create(
            image, sequence_id=1, source_name="test", monotonic_timestamp=0, connection_id=1
        )
        box = BoundingBox(0.2, 0.2, 0.8, 0.9, True)
        detection = Detection(box, "face", 0.9)
        landmarks = ((0.35, 0.4), (0.65, 0.4), (0.5, 0.55), (0.4, 0.7), (0.6, 0.7))
        result = InferenceResult(
            frame, (detection,), InferenceMetrics(detection_count=1), 1, "test",
            {"face_detector": {"landmarks": (landmarks,), "run_id": "r"}},
        )
        aligned = AlignedFace(
            frame, np.zeros((112, 112, 3), dtype=np.uint8), box, landmarks,
            np.eye(2, 3), np.eye(2, 3), 0, 0.9, "r", AlignmentStatus.ALIGNED,
            AlignmentQuality.VALID, None, 1.0, 0.2, 0.4, 1.0,
        )
        diagnostic = draw_diagnostic(image, result, (aligned,))
        self.assertEqual(diagnostic.shape, image.shape)
        self.assertGreater(np.count_nonzero(diagnostic), 0)


if __name__ == "__main__":
    unittest.main()
