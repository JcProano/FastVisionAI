"""Deterministic detector used for development and tests."""

from __future__ import annotations

import time

from src.engine.config import SimulatedDetectorConfig
from src.engine.contracts.detection import BoundingBox, Detection
from src.engine.contracts.inference_context import InferenceContext
from src.engine.contracts.prepared_frame import PreparedFrame


class SimulatedDetectorError(RuntimeError):
    pass


class SimulatedDetector:
    def __init__(self, config: SimulatedDetectorConfig) -> None:
        if config.detection_count < 0:
            raise ValueError("detection_count must be non-negative")
        if not 0.0 <= config.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if config.latency_ms < 0:
            raise ValueError("latency_ms must be non-negative")
        self.config = config

    def detect(
        self,
        prepared_frame: PreparedFrame,
        context: InferenceContext,
    ) -> tuple[Detection, ...]:
        del context
        if self.config.latency_ms:
            time.sleep(self.config.latency_ms / 1_000)
        if self.config.fail:
            raise SimulatedDetectorError("Controlled simulated detector failure")

        detections: list[Detection] = []
        count = self.config.detection_count
        for index in range(count):
            fraction = (index + 1) / (count + 1)
            x1 = prepared_frame.width * fraction * 0.5
            y1 = prepared_frame.height * fraction * 0.5
            detections.append(
                Detection(
                    bounding_box=BoundingBox(
                        x1=x1,
                        y1=y1,
                        x2=min(float(prepared_frame.width), x1 + prepared_frame.width * 0.25),
                        y2=min(float(prepared_frame.height), y1 + prepared_frame.height * 0.4),
                    ),
                    class_name=self.config.class_name,
                    confidence=self.config.confidence,
                    class_id=0,
                )
            )
        return tuple(detections)
