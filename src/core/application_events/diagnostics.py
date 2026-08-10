"""Bounded scalar-only diagnostics for application event delivery."""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime

from .contracts import ApplicationEvent


@dataclass(frozen=True, slots=True)
class ApplicationEventDiagnostic:
    event_type: str
    timestamp: datetime
    source: str


class ApplicationEventDiagnosticsStore:
    def __init__(self, limit: int = 100) -> None:
        if limit <= 0:
            raise ValueError("diagnostics limit must be positive")
        self.limit = limit
        self._items: deque[ApplicationEventDiagnostic] = deque(maxlen=limit)
        self._lock = threading.RLock()

    def record(self, event: ApplicationEvent) -> None:
        value = ApplicationEventDiagnostic(
            event.event_type, event.timestamp, event.source,
        )
        with self._lock:
            self._items.append(value)

    def snapshot(self) -> tuple[ApplicationEventDiagnostic, ...]:
        with self._lock:
            return tuple(self._items)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

