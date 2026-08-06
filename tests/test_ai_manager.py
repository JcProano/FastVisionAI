from __future__ import annotations

import unittest

import numpy as np

from src.camera.frame import Frame
from src.engine.ai_manager import AIManager
from src.engine.backends.simulated import SimulatedInferenceBackend
from src.engine.config import QueueConfig, QueuePolicy, SimulatedDetectorConfig
from src.engine.detectors.simulated import SimulatedDetector
from src.engine.preprocessor import MinimalPreprocessor


def frame(sequence_id: int, valid: bool = True) -> Frame:
    image = np.zeros((20, 30, 3), dtype=np.uint8) if valid else np.array([])
    return Frame.create(
        image,
        sequence_id=sequence_id,
        source_name="test",
        monotonic_timestamp=float(sequence_id),
        connection_id=1,
    )


def manager(detector_config: SimulatedDetectorConfig | None = None) -> AIManager:
    detector = SimulatedDetector(detector_config or SimulatedDetectorConfig())
    return AIManager(
        QueueConfig(capacity=4, policy=QueuePolicy.VIDEO_FILE, wait_timeout_seconds=0.2),
        MinimalPreprocessor(),
        SimulatedInferenceBackend(detector),
    )


class AIManagerTests(unittest.TestCase):
    def test_processes_frame_and_stops_cleanly(self) -> None:
        ai = manager()
        ai.start()
        original = frame(1)
        self.assertTrue(ai.submit(original))
        result = ai.get_result(timeout=1)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertIs(result.frame, original)
        self.assertTrue(ai.stop())
        self.assertFalse(ai.running)
        self.assertEqual(ai.pipeline_metrics().frames_processed, 1)

    def test_invalid_frame_error_isolated_from_worker(self) -> None:
        ai = manager()
        ai.start()
        ai.submit(frame(1, valid=False))
        ai.submit(frame(2))
        result = ai.get_result(timeout=1)
        self.assertIsNotNone(result)
        self.assertTrue(ai.running)
        self.assertTrue(ai.stop())
        self.assertEqual(ai.pipeline_metrics().preprocessing_errors, 1)

    def test_inference_error_isolated_from_manager(self) -> None:
        ai = manager(SimulatedDetectorConfig(fail=True))
        ai.start()
        ai.submit(frame(1))
        self.assertIsNone(ai.get_result(timeout=0.1))
        self.assertTrue(ai.running)
        self.assertTrue(ai.stop())
        self.assertEqual(ai.pipeline_metrics().inference_errors, 1)

    def test_submit_after_stop_is_rejected(self) -> None:
        ai = manager()
        ai.start()
        self.assertTrue(ai.stop())
        self.assertFalse(ai.submit(frame(1)))


if __name__ == "__main__":
    unittest.main()
