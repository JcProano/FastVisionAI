"""Capacity-one projection of copied presentation frames for web clients."""
from __future__ import annotations
import threading
import time
from src.ui.contracts import VisualFrameDTO


class LatestPresentationFrameStore:
    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._frame: VisualFrameDTO | None = None
        self._published_at: float | None = None
        self._closed = False

    @property
    def closed(self) -> bool:
        with self._condition: return self._closed

    def publish(self, frame: VisualFrameDTO) -> bool:
        if not isinstance(frame, VisualFrameDTO): raise TypeError("presentation frame is invalid")
        owned = VisualFrameDTO(frame.width, frame.height, bytes(frame.rgb_bytes), frame.sequence_id)
        with self._condition:
            if self._closed: return False
            self._frame = owned
            self._published_at = time.monotonic()
            self._condition.notify_all()
        return True

    def latest(self) -> VisualFrameDTO | None:
        with self._condition: return self._frame

    def status(self, stale_after_seconds: float = 5.0) -> dict[str, object]:
        with self._condition:
            frame = self._frame
            age = None if self._published_at is None else max(0.0, time.monotonic() - self._published_at)
            return {"available": frame is not None, "stale": frame is None or (age is not None and age > stale_after_seconds), "age_seconds": age, "width": None if frame is None else frame.width, "height": None if frame is None else frame.height, "sequence_id": None if frame is None else frame.sequence_id}

    def wait_for_new(self, sequence_id: int | None, timeout: float = 1.0) -> VisualFrameDTO | None:
        with self._condition:
            self._condition.wait_for(lambda: self._closed or (self._frame is not None and self._frame.sequence_id != sequence_id), timeout)
            return None if self._closed else self._frame

    def close(self) -> None:
        with self._condition:
            if self._closed: return
            self._closed = True; self._frame = None; self._published_at = None; self._condition.notify_all()
