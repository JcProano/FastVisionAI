from __future__ import annotations

import threading
import time
import unittest
from types import SimpleNamespace

import numpy as np

from src.camera.camera_types import CameraReadResult, ReadStatus
from src.camera.frame import Frame
from src.engine.contracts.detection import BoundingBox, Detection, InferenceResult
from src.engine.contracts.metrics import InferenceMetrics, PipelineMetrics
from src.validation.live_person_detection import LiveOptions, build_parser, normalized_box_to_pixels, run_capture_loop


def frame(sequence: int, age: float = 0.0) -> Frame:
    return Frame.create(np.zeros((48, 64, 3), dtype=np.uint8), sequence_id=sequence,
                        source_name="mock", monotonic_timestamp=time.monotonic() - age, connection_id=1)


class FakeCamera:
    connected = False
    def __init__(self, count): self.items = [CameraReadResult(ReadStatus.FRAME, frame(i)) for i in range(count)]
    def open(self): self.connected = True; return True
    def read(self): return self.items.pop(0)
    def release(self): self.connected = False


class FakeAI:
    def __init__(self, stale=False): self.submitted = []; self.results = []; self.stale = stale
    def submit(self, item):
        self.submitted.append(item)
        source = frame(item.sequence_id, age=5 if self.stale else 0)
        self.results.append(InferenceResult(source, (), InferenceMetrics(), 1, "mock"))
        return True
    def get_result(self, timeout=None): return self.results.pop(0) if self.results else None
    def pipeline_metrics(self): return PipelineMetrics(frames_submitted=len(self.submitted), frames_processed=len(self.submitted), average_pipeline_latency_ms=2)
    def queue_metrics(self): return SimpleNamespace(frames_dropped=0)


class LiveValidationTests(unittest.TestCase):
    def test_headless_mock_loop_honors_max_frames(self):
        metrics = run_capture_loop(FakeCamera(3), FakeAI(), LiveOptions(min_inference_interval=0, max_frames=3, no_display=True), threading.Event())
        self.assertEqual(metrics.frames_captured, 3)
        self.assertEqual(metrics.frames_submitted, 3)
        self.assertEqual(metrics.frames_processed, 3)
        self.assertEqual(metrics.actual_resolution, "64x48")

    def test_stale_results_are_omitted(self):
        metrics = run_capture_loop(FakeCamera(2), FakeAI(stale=True), LiveOptions(min_inference_interval=0, result_max_age=1.5, max_frames=2, no_display=True), threading.Event())
        self.assertEqual(metrics.stale_results_omitted, 2)

    def test_box_conversion_and_cli(self):
        detection = Detection(BoundingBox(0.1, 0.2, 0.5, 0.8, normalized=True), "person", 0.9)
        result = InferenceResult(frame(1), (detection,), InferenceMetrics(), 1, "mock")
        self.assertEqual(normalized_box_to_pixels(result, 100, 50)[0][:4], (10, 10, 50, 40))
        args = build_parser().parse_args(["--source", "0", "--no-display", "--max-frames", "5", "--result-max-age", "2"])
        self.assertTrue(args.no_display)
        self.assertEqual(args.max_frames, 5)
        self.assertEqual(args.result_max_age, 2)


if __name__ == "__main__": unittest.main()
