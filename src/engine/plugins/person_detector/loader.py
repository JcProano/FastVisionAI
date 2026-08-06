"""Lazy Ultralytics implementation of the ModelLoader contract."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from src.engine.models.contracts import ModelSpec


@dataclass(slots=True)
class LoadedUltralyticsModel:
    model: object
    weights_sha256: str


class UltralyticsModelLoader:
    def load(self, spec: ModelSpec) -> LoadedUltralyticsModel:
        from ultralytics import YOLO  # Lazy by design; no import during discovery.

        digest = hashlib.sha256(spec.artifact_path.read_bytes()).hexdigest()
        return LoadedUltralyticsModel(YOLO(str(spec.artifact_path)), digest)

    def unload(self, model: object) -> None:
        if isinstance(model, LoadedUltralyticsModel):
            model.model = None
