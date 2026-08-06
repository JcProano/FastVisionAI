"""Specialized multi-face detection backend powered by OpenCV YuNet."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Mapping

from src.engine.capabilities.contracts import Capability
from src.engine.contracts.detection import BoundingBox, Detection, InferenceResult
from src.engine.contracts.inference_context import InferenceContext
from src.engine.contracts.metrics import InferenceMetrics
from src.engine.contracts.prepared_frame import PreparedFrame
from src.engine.models.contracts import ModelBackend, ModelSpec
from src.engine.plugins.contracts import PluginDescriptor
from src.engine.plugins.face_detector.loader import LoadedYuNetModel, OpenCVYuNetModelLoader
from src.engine.plugins.services import PluginServices

PLUGIN_DESCRIPTOR = PluginDescriptor(
    id="face_detector",
    name="Face Detector",
    version="1.0.0",
    api_version="1.0",
    author="FastVisionAI",
    description="OpenCV YuNet multi-face detection",
    backend="opencv_yunet",
    capabilities=(Capability("face_detection", "vision", False),),
    priority=10,
    enabled=False,
)


class FaceDetectorPlugin:
    def __init__(self, settings: Mapping[str, Any], services: PluginServices) -> None:
        self.manager = services.model_manager
        self.alias = str(settings.get("model_alias", "face_detector_default"))
        self.model_path = Path(
            str(settings.get("model_path", "models/face/face_detection_yunet_2026may.onnx"))
        )
        self.confidence = float(settings.get("confidence", 0.6))
        self.nms_threshold = float(settings.get("nms_threshold", 0.3))
        self.top_k = int(settings.get("top_k", 5000))
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if not 0.0 <= self.nms_threshold <= 1.0:
            raise ValueError("nms_threshold must be between 0 and 1")
        if self.top_k <= 0:
            raise ValueError("top_k must be positive")

        self.manager.register_loader(ModelBackend.ONNX_RUNTIME, OpenCVYuNetModelLoader())
        spec = ModelSpec(
            name="face_detection_yunet",
            version="2026may",
            backend=ModelBackend.ONNX_RUNTIME,
            artifact_path=self.model_path,
            metadata={
                "confidence": self.confidence,
                "nms_threshold": self.nms_threshold,
                "top_k": self.top_k,
            },
        )
        if not self.manager.exists(spec.key):
            self.manager.register(spec)
        self.manager.set_alias(self.alias, spec.key)

    @property
    def name(self) -> str:
        return PLUGIN_DESCRIPTOR.id

    def infer(self, prepared_frame: PreparedFrame, context: InferenceContext) -> InferenceResult:
        started = time.monotonic()
        loaded = self.manager.get_model_by_alias(self.alias)
        if not isinstance(loaded, LoadedYuNetModel):
            raise TypeError("Unexpected model object for FaceDetectorPlugin")

        inference_started = time.monotonic()
        loaded.detector.setInputSize((prepared_frame.width, prepared_frame.height))
        _, faces = loaded.detector.detect(prepared_frame.image)
        detections: list[Detection] = []
        landmarks: list[tuple[tuple[float, float], ...]] = []
        for row in () if faces is None else faces:
            confidence = float(row[14])
            if confidence < self.confidence:
                continue
            x, y, width, height = (float(value) for value in row[:4])
            x1 = _clamp(x / prepared_frame.width)
            y1 = _clamp(y / prepared_frame.height)
            x2 = _clamp((x + width) / prepared_frame.width)
            y2 = _clamp((y + height) / prepared_frame.height)
            detections.append(
                Detection(
                    bounding_box=BoundingBox(x1, y1, x2, y2, normalized=True),
                    class_name="face",
                    confidence=confidence,
                    class_id=0,
                )
            )
            landmarks.append(
                tuple(
                    (
                        _clamp(float(row[index]) / prepared_frame.width),
                        _clamp(float(row[index + 1]) / prepared_frame.height),
                    )
                    for index in range(4, 14, 2)
                )
            )

        inference_ms = (time.monotonic() - inference_started) * 1_000
        elapsed_ms = (time.monotonic() - started) * 1_000
        return InferenceResult(
            frame=prepared_frame.frame,
            detections=tuple(detections),
            metrics=InferenceMetrics(inference_ms=inference_ms, detection_count=len(detections)),
            latency_ms=elapsed_ms,
            backend="opencv_yunet",
            attachments={
                "run_id": context.run_id,
                "model_alias": self.alias,
                "weights_sha256": loaded.weights_sha256,
                "load_time_ms": loaded.load_time_ms,
                "device": context.device,
                "landmarks": tuple(landmarks),
            },
        )

    def release(self) -> None:
        self.manager.unload(self.manager.resolve_alias(self.alias))


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))


def create_plugin(settings: Mapping[str, Any], services: PluginServices) -> FaceDetectorPlugin:
    return FaceDetectorPlugin(settings, services)
