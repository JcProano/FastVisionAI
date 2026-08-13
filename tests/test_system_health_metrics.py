import threading,unittest
from src.core.system_health import RollingPerformanceMetrics
class MetricsTests(unittest.TestCase):
 def test_window_fps_interval_and_nd_latency(self):
  now=[0.0];metrics=RollingPerformanceMetrics(2,monotonic=lambda:now[0],memory_reader=lambda:12.5)
  for value in (0,0.5,1.0):metrics.observe_frame(value)
  result=metrics.snapshot();self.assertAlmostEqual(result.fps,2);self.assertAlmostEqual(result.frame_interval_ms,500);self.assertIsNone(result.processing_latency_ms);self.assertIsNone(result.inference_latency_ms)
  now[0]=4;self.assertIsNone(metrics.snapshot().fps)
 def test_memory_unavailable_and_counters(self):
  metrics=RollingPerformanceMetrics(memory_reader=lambda:None);metrics.observe_counters(queue_depth=2,dropped_frames=3);result=metrics.snapshot();self.assertIsNone(result.memory_usage_mb);self.assertEqual((result.queue_depth,result.dropped_frames),(2,3))
 def test_concurrent_observe_read(self):
  metrics=RollingPerformanceMetrics(10);threads=[threading.Thread(target=lambda:[metrics.observe_frame() for _ in range(100)]) for _ in range(4)]
  for thread in threads:thread.start()
  for thread in threads:thread.join()
  self.assertIsNotNone(metrics.snapshot())
