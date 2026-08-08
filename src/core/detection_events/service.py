"""Cooldown and safe failure isolation for observation events."""
from __future__ import annotations
import logging
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Callable

from .contracts import (
    DetectionEventInput, DetectionEventRecord, DetectionEventType,
    DetectionEventWriteResult,
)
from .repository import DetectionEventRepository

LOGGER = logging.getLogger(__name__)


class DetectionEventService:
    def __init__(self, repository: DetectionEventRepository, *,
                 registered_cooldown_seconds: float = 60.0,
                 unregistered_cooldown_seconds: float = 60.0,
                 cache_limit: int = 500,
                 monotonic: Callable[[], float] = time.monotonic,
                 utcnow: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> None:
        if min(registered_cooldown_seconds, unregistered_cooldown_seconds) < 0:
            raise ValueError("cooldowns must be non-negative")
        if cache_limit <= 0: raise ValueError("cache_limit must be positive")
        self.repository = repository
        self.registered_cooldown_seconds = registered_cooldown_seconds
        self.unregistered_cooldown_seconds = unregistered_cooldown_seconds
        self._monotonic = monotonic; self._utcnow = utcnow
        self._last: dict[tuple[object, ...], float] = {}
        self._cache: deque[DetectionEventRecord] = deque(maxlen=cache_limit)
        self._lock = threading.RLock()

    def observe(self, item: DetectionEventInput) -> DetectionEventWriteResult:
        key = ((item.event_type.value, item.person_id, item.camera_id)
               if item.event_type is DetectionEventType.REGISTERED_CANDIDATE
               else (item.event_type.value, item.camera_id))
        cooldown = (self.registered_cooldown_seconds
                    if item.event_type is DetectionEventType.REGISTERED_CANDIDATE
                    else self.unregistered_cooldown_seconds)
        with self._lock:
            now = self._monotonic()
            if now - self._last.get(key, float("-inf")) < cooldown:
                return DetectionEventWriteResult(True, False, None, "cooldown")
            event = DetectionEventRecord(
                str(uuid.uuid4()), item.person_id, item.event_type, item.timestamp,
                item.camera_id, item.display_name_snapshot, item.similarity,
                item.quality_score, item.recognition_state, item.administrative_status,
                item.session_id, self._utcnow(),
            )
            try:
                self.repository.create(event)
            except Exception:
                LOGGER.warning("Detection event persistence failed; event_type=%s camera_id=%s",
                               item.event_type.value, item.camera_id)
                return DetectionEventWriteResult(False, False, None, "persistence_error")
            self._last[key] = now
            self._cache.appendleft(event)
            return DetectionEventWriteResult(True, True, event, "recorded")

    def recent(self, limit: int = 20) -> tuple[DetectionEventRecord, ...]:
        if limit <= 0: return ()
        with self._lock: return tuple(list(self._cache)[:limit])

