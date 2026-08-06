"""Bounded, cancellation-aware Frame queue."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass

from src.engine.config import QueuePolicy
from src.engine.contracts.frame import Frame


@dataclass(frozen=True, slots=True)
class FrameQueueMetrics:
    frames_received: int
    frames_delivered: int
    frames_dropped: int
    current_size: int
    maximum_size_reached: int


@dataclass(frozen=True, slots=True)
class _QueuedFrame:
    frame: Frame
    enqueued_at: float


class FrameQueue:
    def __init__(self, capacity: int, policy: QueuePolicy) -> None:
        if capacity <= 0:
            raise ValueError("FrameQueue capacity must be positive")
        self.capacity = capacity
        self.policy = policy
        self._items: deque[_QueuedFrame] = deque()
        self._condition = threading.Condition()
        self._cancelled = False
        self._received = 0
        self._delivered = 0
        self._dropped = 0
        self._maximum_size = 0

    @property
    def cancelled(self) -> bool:
        with self._condition:
            return self._cancelled

    def put(self, frame: Frame, timeout: float | None = None) -> bool:
        """Insert a frame or return False when cancelled/timed out."""

        deadline = None if timeout is None else time.monotonic() + timeout
        with self._condition:
            if self._cancelled:
                return False
            if self.policy is QueuePolicy.REALTIME and len(self._items) >= self.capacity:
                self._items.popleft()
                self._dropped += 1
            while self.policy is QueuePolicy.VIDEO_FILE and len(self._items) >= self.capacity:
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    return False
                self._condition.wait(remaining)
                if self._cancelled:
                    return False
            self._items.append(_QueuedFrame(frame, time.monotonic()))
            self._received += 1
            self._maximum_size = max(self._maximum_size, len(self._items))
            self._condition.notify_all()
            return True

    def get(self, timeout: float | None = None) -> Frame | None:
        """Return the next frame, or None on cancellation/timeout."""

        item = self.get_with_wait(timeout)
        return None if item is None else item[0]

    def get_with_wait(self, timeout: float | None = None) -> tuple[Frame, float] | None:
        """Return a frame and its exact queue wait in milliseconds."""

        deadline = None if timeout is None else time.monotonic() + timeout
        with self._condition:
            while not self._items:
                if self._cancelled:
                    return None
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    return None
                self._condition.wait(remaining)
            queued = self._items.popleft()
            self._delivered += 1
            self._condition.notify_all()
            wait_ms = max(0.0, (time.monotonic() - queued.enqueued_at) * 1_000)
            return queued.frame, wait_ms

    def cancel(self) -> None:
        with self._condition:
            self._cancelled = True
            self._items.clear()
            self._condition.notify_all()

    def metrics(self) -> FrameQueueMetrics:
        with self._condition:
            return FrameQueueMetrics(
                frames_received=self._received,
                frames_delivered=self._delivered,
                frames_dropped=self._dropped,
                current_size=len(self._items),
                maximum_size_reached=self._maximum_size,
            )
