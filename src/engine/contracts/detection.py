"""Detection and inference result contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.engine.contracts.frame import Frame
from src.engine.contracts.metrics import InferenceMetrics


@dataclass(frozen=True, slots=True)
class BoundingBox:
    x1: float
    y1: float
    x2: float
    y2: float
    normalized: bool = False

    def __post_init__(self) -> None:
        if self.x2 < self.x1 or self.y2 < self.y1:
            raise ValueError("BoundingBox coordinates must be ordered")
        if self.normalized and not all(0.0 <= value <= 1.0 for value in (self.x1, self.y1, self.x2, self.y2)):
            raise ValueError("Normalized BoundingBox coordinates must be between 0 and 1")

    @property
    def width(self) -> float:
        return self.x2 - self.x1

    @property
    def height(self) -> float:
        return self.y2 - self.y1


@dataclass(frozen=True, slots=True)
class Detection:
    bounding_box: BoundingBox
    class_name: str
    confidence: float
    class_id: int = 0

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Detection confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class InferenceResult:
    frame: Frame
    detections: tuple[Detection, ...]
    metrics: InferenceMetrics
    latency_ms: float
    backend: str
    attachments: dict[str, Any] = field(default_factory=dict)
