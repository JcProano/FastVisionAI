from __future__ import annotations

import unittest

import numpy as np

from src.camera.frame import Frame
from src.engine.backends.simulated import SimulatedInferenceBackend
from src.engine.config import SimulatedDetectorConfig
from src.engine.contracts.detector import Detector, InferenceBackend
from src.engine.contracts.inference_context import InferenceContext
from src.engine.detectors.simulated import SimulatedDetector, SimulatedDetectorError
from src.engine.preprocessor import InvalidFrameError, MinimalPreprocessor


def make_frame(image: object) -> Frame:
    return Frame.create(
        image,
        sequence_id=4,
        source_name="synthetic",
        monotonic_timestamp=1.0,
        connection_id=1,
    )


class PipelineComponentTests(unittest.TestCase):
    def test_preprocessor_preserves_original_references(self) -> None:
        image = np.zeros((100, 200, 3), dtype=np.uint8)
        frame = make_frame(image)
        prepared = MinimalPreprocessor().prepare(frame)
        self.assertIs(prepared.frame, frame)
        self.assertIs(prepared.image, image)
        self.assertEqual((prepared.width, prepared.height), (200, 100))

    def test_preprocessor_rejects_empty_frame(self) -> None:
        with self.assertRaises(InvalidFrameError):
            MinimalPreprocessor().prepare(make_frame(np.array([], dtype=np.uint8)))

    def test_simulated_detector_is_deterministic(self) -> None:
        config = SimulatedDetectorConfig(
            detection_count=2,
            class_name="person",
            confidence=0.75,
        )
        detector = SimulatedDetector(config)
        self.assertIsInstance(detector, Detector)
        prepared = MinimalPreprocessor().prepare(make_frame(np.zeros((100, 200, 3))))
        first = detector.detect(prepared, InferenceContext())
        second = detector.detect(prepared, InferenceContext())
        self.assertEqual(first, second)
        self.assertEqual(len(first), 2)
        self.assertTrue(all(item.class_name == "person" for item in first))

    def test_simulated_backend_returns_inference_result(self) -> None:
        frame = make_frame(np.zeros((80, 120, 3)))
        prepared = MinimalPreprocessor().prepare(frame)
        backend = SimulatedInferenceBackend(SimulatedDetector(SimulatedDetectorConfig()))
        self.assertIsInstance(backend, InferenceBackend)
        result = backend.infer(prepared, InferenceContext())
        self.assertIs(result.frame, frame)
        self.assertEqual(result.backend, "simulated")
        self.assertEqual(len(result.detections), 1)
        self.assertGreaterEqual(result.latency_ms, 0)

    def test_controlled_detector_error(self) -> None:
        detector = SimulatedDetector(SimulatedDetectorConfig(fail=True))
        prepared = MinimalPreprocessor().prepare(make_frame(np.zeros((10, 10, 3))))
        with self.assertRaises(SimulatedDetectorError):
            detector.detect(prepared, InferenceContext())


if __name__ == "__main__":
    unittest.main()
