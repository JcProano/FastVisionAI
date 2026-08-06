"""Example plugin producing deterministic, valid inference output."""

from __future__ import annotations

import time
from typing import Any, Mapping

from src.engine.capabilities.contracts import Capability
from src.engine.contracts.detection import BoundingBox, Detection, InferenceResult
from src.engine.contracts.inference_context import InferenceContext
from src.engine.contracts.metrics import InferenceMetrics
from src.engine.contracts.prepared_frame import PreparedFrame
from src.engine.plugins.contracts import PluginDescriptor
from src.engine.plugins.services import PluginServices

PLUGIN_DESCRIPTOR = PluginDescriptor(
    id="dummy",
    name="Dummy Plugin",
    version="1.0.0",
    api_version="1.0",
    author="FastVisionAI",
    description="Deterministic example backend without a real model",
    backend="dummy",
    capabilities=(
        Capability("detection", "vision", experimental=False),
        Capability("testing", "development", experimental=True),
    ),
    priority=100,
    enabled=False,
)


class DummyPlugin:
    def __init__(self, settings: Mapping[str, Any]) -> None:
        self.detection_count = int(settings.get("detection_count", 1))
        self.class_name = str(settings.get("class_name", "person"))
        self.confidence = float(settings.get("confidence", 0.9))
        self.latency_ms = float(settings.get("latency_ms", 0.0))
        self.fail = bool(settings.get("fail", False))
        if self.detection_count < 0 or self.latency_ms < 0:
            raise ValueError("DummyPlugin counts and latency must be non-negative")
        if not 0 <= self.confidence <= 1:
            raise ValueError("DummyPlugin confidence must be between 0 and 1")

    @property
    def name(self) -> str:
        return PLUGIN_DESCRIPTOR.id

    def infer(
        self,
        prepared_frame: PreparedFrame,
        context: InferenceContext,
    ) -> InferenceResult:
        started = time.monotonic()
        if self.latency_ms:
            time.sleep(self.latency_ms / 1_000)
        if self.fail:
            raise RuntimeError("Controlled DummyPlugin failure")
        detections = tuple(
            Detection(
                bounding_box=BoundingBox(
                    x1=float(index * 5),
                    y1=float(index * 5),
                    x2=min(float(prepared_frame.width), float(index * 5 + 20)),
                    y2=min(float(prepared_frame.height), float(index * 5 + 30)),
                ),
                class_name=self.class_name,
                confidence=self.confidence,
            )
            for index in range(self.detection_count)
        )
        elapsed_ms = (time.monotonic() - started) * 1_000
        return InferenceResult(
            frame=prepared_frame.frame,
            detections=detections,
            metrics=InferenceMetrics(inference_ms=elapsed_ms, detection_count=len(detections)),
            latency_ms=elapsed_ms,
            backend=self.name,
            attachments={"run_id": context.run_id, "plugin_version": PLUGIN_DESCRIPTOR.version},
        )


def create_plugin(settings: Mapping[str, Any], services: PluginServices) -> DummyPlugin:
    del services
    return DummyPlugin(settings)
