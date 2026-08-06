"""Lazy OpenCV-DNN loader for an ArcFace-compatible ONNX model."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Any

from src.engine.models.contracts import ModelSpec


@dataclass(slots=True)
class LoadedArcFaceModel:
    network: Any
    weights_sha256: str
    load_time_ms: float


class OpenCVArcFaceModelLoader:
    def load(self, spec: ModelSpec) -> LoadedArcFaceModel:
        import cv2  # Lazy: discovery and construction do not import a model runtime.

        started = time.monotonic()
        digest = hashlib.sha256(spec.artifact_path.read_bytes()).hexdigest()
        network = cv2.dnn.readNetFromONNX(str(spec.artifact_path))
        return LoadedArcFaceModel(
            network=network,
            weights_sha256=digest,
            load_time_ms=(time.monotonic() - started) * 1_000,
        )

    def unload(self, model: object) -> None:
        if isinstance(model, LoadedArcFaceModel):
            model.network = None
