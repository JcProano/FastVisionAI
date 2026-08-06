from __future__ import annotations

import unittest

import numpy as np

from src.camera.frame import Frame
from src.engine.contracts.detection import BoundingBox, Detection, InferenceResult
from src.engine.contracts.metrics import InferenceMetrics
from src.validation.static_face_detection import annotate


class StaticFaceDetectionTests(unittest.TestCase):
    def test_annotate_preserves_resolution(self):
        image = np.zeros((80, 120, 3), dtype=np.uint8)
        frame = Frame.create(
            image, sequence_id=1, source_name="static", monotonic_timestamp=0, connection_id=1
        )
        result = InferenceResult(
            frame=frame,
            detections=(Detection(BoundingBox(0.1, 0.1, 0.5, 0.6, True), "face", 0.9),),
            metrics=InferenceMetrics(detection_count=1),
            latency_ms=1.0,
            backend="test",
        )
        output = annotate(image, result)
        self.assertEqual(output.shape, image.shape)
        self.assertFalse(np.shares_memory(output, image))


if __name__ == "__main__":
    unittest.main()
