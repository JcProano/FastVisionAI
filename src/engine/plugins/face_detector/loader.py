"""OpenCV YuNet implementation of the model-loader contract."""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from typing import Any

from src.engine.models.contracts import ModelSpec


@dataclass(slots=True)
class LoadedYuNetModel:
    detector: Any
    weights_sha256: str
    load_time_ms: float = 0.0


class OpenCVYuNetModelLoader:
    """Load YuNet lazily without importing OpenCV during plugin discovery."""

    def load(self, spec: ModelSpec) -> LoadedYuNetModel:
        import cv2  # Lazy by design.

        started = time.monotonic()
        digest = hashlib.sha256(spec.artifact_path.read_bytes()).hexdigest()
        metadata = spec.metadata
        detector = cv2.FaceDetectorYN.create(
            str(spec.artifact_path),
            "",
            (320, 320),
            float(metadata.get("confidence", 0.6)),
            float(metadata.get("nms_threshold", 0.3)),
            int(metadata.get("top_k", 5000)),
        )
        return LoadedYuNetModel(
            detector=detector,
            weights_sha256=digest,
            load_time_ms=(time.monotonic() - started) * 1_000,
        )

    def unload(self, model: object) -> None:
        if isinstance(model, LoadedYuNetModel):
            model.detector = None
