from __future__ import annotations

import unittest

from src.engine.benchmark.manager import BenchmarkManager


class BenchmarkManagerTests(unittest.TestCase):
    def test_collects_pipeline_plugin_and_queue_metrics(self) -> None:
        benchmark = BenchmarkManager()
        benchmark.record_frame_started(queue_wait_ms=4)
        benchmark.record_frame_completed(latency_ms=10)
        benchmark.record_plugin("dummy", elapsed_ms=6)
        benchmark.record_plugin("dummy", elapsed_ms=8, error=True)
        benchmark.update_frames_dropped(3)
        snapshot = benchmark.snapshot()
        self.assertEqual(snapshot.frames_started, 1)
        self.assertEqual(snapshot.frames_completed, 1)
        self.assertEqual(snapshot.frames_dropped, 3)
        self.assertEqual(snapshot.average_latency_ms, 10)
        self.assertEqual(snapshot.average_queue_wait_ms, 4)
        self.assertEqual(snapshot.total_queue_wait_ms, 4)
        self.assertEqual(snapshot.plugins[0].average_time_ms, 7)
        self.assertEqual(snapshot.plugins[0].errors, 1)
        self.assertGreaterEqual(snapshot.fps, 0)

    def test_reset_clears_metrics(self) -> None:
        benchmark = BenchmarkManager()
        benchmark.record_frame_started(2)
        benchmark.record_frame_completed(3)
        benchmark.reset()
        snapshot = benchmark.snapshot()
        self.assertEqual(snapshot.frames_started, 0)
        self.assertEqual(snapshot.frames_completed, 0)
        self.assertEqual(snapshot.plugins, ())


if __name__ == "__main__":
    unittest.main()
