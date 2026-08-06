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
from src.engine.plugins.person_detector.loader import LoadedUltralyticsModel, UltralyticsModelLoader
from src.engine.plugins.services import PluginServices

PLUGIN_DESCRIPTOR = PluginDescriptor(
    id="person_detector", name="Person Detector", version="1.0.0", api_version="1.0",
    author="FastVisionAI", description="YOLOv8 person and configurable class detection",
    backend="ultralytics", capabilities=(Capability("person_detection", "vision", False),),
    priority=10, enabled=False,
)


class PersonDetectorPlugin:
    def __init__(self, settings: Mapping[str, Any], services: PluginServices) -> None:
        self.manager = services.model_manager
        self.alias = str(settings.get("model_alias", "person_detector_default"))
        self.model_name = str(settings.get("model_name", "yolov8n"))
        self.model_version = str(settings.get("model_version", "8"))
        self.model_path = Path(str(settings.get("model_path", "models/yolo/yolov8n.pt")))
        self.confidence = float(settings.get("confidence", 0.4))
        self.iou = float(settings.get("iou_threshold", 0.45))
        self.image_size = int(settings.get("image_size", 640))
        self.allowed_classes = tuple(int(value) for value in settings.get("allowed_classes", [0]))
        self.manager.register_loader(ModelBackend.PYTORCH, UltralyticsModelLoader())
        spec = ModelSpec(self.model_name, self.model_version, ModelBackend.PYTORCH, self.model_path)
        if not self.manager.exists(spec.key):
            self.manager.register(spec)
        self.manager.set_alias(self.alias, spec.key)

    @property
    def name(self) -> str:
        return PLUGIN_DESCRIPTOR.id

    def infer(self, prepared_frame: PreparedFrame, context: InferenceContext) -> InferenceResult:
        started = time.monotonic()
        loaded = self.manager.get_model_by_alias(self.alias)
        if not isinstance(loaded, LoadedUltralyticsModel):
            raise TypeError("Unexpected model object for PersonDetectorPlugin")
        results = loaded.model.predict(
            source=prepared_frame.image, conf=self.confidence, iou=self.iou,
            imgsz=self.image_size, device=context.device, verbose=False,
        )
        detections: list[Detection] = []
        candidates = 0
        for result in results:
            boxes = getattr(result, "boxes", ())
            for box in boxes:
                candidates += 1
                class_id = int(box.cls[0])
                confidence = float(box.conf[0])
                if class_id not in self.allowed_classes or confidence < self.confidence:
                    continue
                x1, y1, x2, y2 = (float(value) for value in box.xyxy[0])
                detections.append(Detection(
                    BoundingBox(x1 / prepared_frame.width, y1 / prepared_frame.height,
                                x2 / prepared_frame.width, y2 / prepared_frame.height, normalized=True),
                    str(getattr(result, "names", {}).get(class_id, class_id)), confidence, class_id,
                ))
        elapsed = (time.monotonic() - started) * 1000
        return InferenceResult(
            frame=prepared_frame.frame, detections=tuple(detections),
            metrics=InferenceMetrics(inference_ms=elapsed, detection_count=len(detections)),
            latency_ms=elapsed, backend="ultralytics",
            attachments={"run_id": context.run_id, "model_alias": self.alias,
                         "model_version": self.model_version, "weights_sha256": loaded.weights_sha256,
                         "device": context.device, "candidates": candidates},
        )

    def release(self) -> None:
        self.manager.unload(self.manager.resolve_alias(self.alias))


def create_plugin(settings: Mapping[str, Any], services: PluginServices) -> PersonDetectorPlugin:
    return PersonDetectorPlugin(settings, services)
