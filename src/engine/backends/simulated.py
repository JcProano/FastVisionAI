"""Backend adapter around the simulated Detector contract."""

from __future__ import annotations

import time

from src.engine.contracts.detection import InferenceResult
from src.engine.contracts.detector import Detector
from src.engine.contracts.inference_context import InferenceContext
from src.engine.contracts.metrics import InferenceMetrics
from src.engine.contracts.prepared_frame import PreparedFrame


class SimulatedInferenceBackend:
    def __init__(self, detector: Detector) -> None:
        self.detector = detector

    @property
    def name(self) -> str:
        return "simulated"

    def infer(
        self,
        prepared_frame: PreparedFrame,
        context: InferenceContext,
    ) -> InferenceResult:
        started = time.monotonic()
        detections = self.detector.detect(prepared_frame, context)
        inference_ms = (time.monotonic() - started) * 1_000
        return InferenceResult(
            frame=prepared_frame.frame,
            detections=detections,
            metrics=InferenceMetrics(
                inference_ms=inference_ms,
                detection_count=len(detections),
            ),
            latency_ms=inference_ms,
            backend=self.name,
        )
