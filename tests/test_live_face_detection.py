from __future__ import annotations

import unittest

import numpy as np

from src.camera.frame import Frame
from src.engine.contracts.detection import BoundingBox, Detection, InferenceResult
from src.engine.contracts.metrics import InferenceMetrics
from src.validation.live_face_detection import build_parser, draw_overlay
from src.validation.live_person_detection import LiveMetrics


class LiveFaceDetectionTests(unittest.TestCase):
    def test_cli_supports_bounded_headless_execution(self):
        args = build_parser().parse_args(["--no-display", "--max-frames", "5"])
        self.assertTrue(args.no_display)
        self.assertEqual(args.max_frames, 5)

    def test_overlay_draws_face_without_changing_resolution(self):
        image = np.zeros((100, 200, 3), dtype=np.uint8)
        frame = Frame.create(
            image, sequence_id=1, source_name="mock", monotonic_timestamp=0, connection_id=1
        )
        result = InferenceResult(
            frame,
            (Detection(BoundingBox(0.1, 0.1, 0.4, 0.5, True), "face", 0.8),),
            InferenceMetrics(detection_count=1),
            1.0,
            "mock",
        )
        metrics = LiveMetrics(1, 1, 1, 0, 0, 1.0, 1.0, 1.0, "200x100", "connected")
        draw_overlay(image, result, metrics)
        self.assertEqual(image.shape, (100, 200, 3))
        self.assertGreater(np.count_nonzero(image), 0)


if __name__ == "__main__":
    unittest.main()
