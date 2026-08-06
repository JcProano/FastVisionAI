from __future__ import annotations

import threading
import time
import unittest

import numpy as np

from src.camera.frame import Frame
from src.engine.config import QueuePolicy
from src.engine.frame_queue import FrameQueue


def make_frame(sequence_id: int) -> Frame:
    return Frame.create(
        np.zeros((10, 20, 3), dtype=np.uint8),
        sequence_id=sequence_id,
        source_name="test",
        monotonic_timestamp=float(sequence_id),
        connection_id=1,
    )


class FrameQueueTests(unittest.TestCase):
    def test_put_and_get_update_metrics(self) -> None:
        frame_queue = FrameQueue(2, QueuePolicy.REALTIME)
        frame = make_frame(1)
        self.assertTrue(frame_queue.put(frame))
        self.assertIs(frame_queue.get(), frame)
        metrics = frame_queue.metrics()
        self.assertEqual(metrics.frames_received, 1)
        self.assertEqual(metrics.frames_delivered, 1)
        self.assertEqual(metrics.frames_dropped, 0)
        self.assertEqual(metrics.current_size, 0)
        self.assertEqual(metrics.maximum_size_reached, 1)

    def test_reports_exact_queue_wait(self) -> None:
        frame_queue = FrameQueue(1, QueuePolicy.REALTIME)
        frame_queue.put(make_frame(1))
        time.sleep(0.002)
        item = frame_queue.get_with_wait()
        self.assertIsNotNone(item)
        assert item is not None
        queued_frame, wait_ms = item
        self.assertEqual(queued_frame.sequence_id, 1)
        self.assertGreaterEqual(wait_ms, 1.0)

    def test_realtime_discards_oldest_frame(self) -> None:
        frame_queue = FrameQueue(2, QueuePolicy.REALTIME)
        frame_queue.put(make_frame(1))
        frame_queue.put(make_frame(2))
        frame_queue.put(make_frame(3))
        first = frame_queue.get()
        second = frame_queue.get()
        self.assertEqual([first.sequence_id, second.sequence_id], [2, 3])  # type: ignore[union-attr]
        self.assertEqual(frame_queue.metrics().frames_dropped, 1)

    def test_video_file_waits_without_dropping(self) -> None:
        frame_queue = FrameQueue(1, QueuePolicy.VIDEO_FILE)
        first = make_frame(1)
        second = make_frame(2)
        frame_queue.put(first)
        inserted = threading.Event()

        def producer() -> None:
            if frame_queue.put(second, timeout=1):
                inserted.set()

        thread = threading.Thread(target=producer)
        thread.start()
        time.sleep(0.02)
        self.assertFalse(inserted.is_set())
        self.assertIs(frame_queue.get(), first)
        thread.join(1)
        self.assertTrue(inserted.is_set())
        self.assertIs(frame_queue.get(), second)
        self.assertEqual(frame_queue.metrics().frames_dropped, 0)

    def test_cancel_unblocks_waiting_consumer_and_producer(self) -> None:
        consumer_queue = FrameQueue(1, QueuePolicy.VIDEO_FILE)
        consumer_result: list[Frame | None] = []
        consumer = threading.Thread(target=lambda: consumer_result.append(consumer_queue.get()))
        consumer.start()
        consumer_queue.cancel()
        consumer.join(1)
        self.assertEqual(consumer_result, [None])

        producer_queue = FrameQueue(1, QueuePolicy.VIDEO_FILE)
        producer_queue.put(make_frame(1))
        producer_result: list[bool] = []
        producer = threading.Thread(
            target=lambda: producer_result.append(producer_queue.put(make_frame(2)))
        )
        producer.start()
        producer_queue.cancel()
        producer.join(1)
        self.assertEqual(producer_result, [False])


if __name__ == "__main__":
    unittest.main()
