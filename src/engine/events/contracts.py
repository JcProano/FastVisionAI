from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class Event:
    run_id: str | None = None
    event_id: str = field(default_factory=lambda: str(uuid4()))
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True, slots=True)
class RuntimeEvent(Event):
    runtime_name: str = ""
    state: str = ""


@dataclass(frozen=True, slots=True)
class InferenceEvent(Event):
    runtime_name: str = ""
    success: bool = True
    latency_ms: float = 0.0
