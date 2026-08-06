"""Biometric postprocessor that generates embeddings from aligned faces.

Despite its functional name, FaceEmbeddingPlugin is not an InferenceBackend
and is not executed by the PreparedFrame scheduler.
"""

from __future__ import annotations

import math
import logging
import threading
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from src.engine.alignment.contracts import AlignedFace, AlignmentQuality, AlignmentStatus
from src.engine.embedding.contracts import FaceEmbedding, FaceEmbeddingMetrics
from src.engine.embedding.loader import LoadedArcFaceModel, OpenCVArcFaceModelLoader
from src.engine.models.contracts import ModelBackend, ModelSpec
from src.engine.models.manager import ModelManager

LOGGER = logging.getLogger(__name__)


class FaceEmbeddingError(RuntimeError):
    pass


class InvalidAlignedFaceError(FaceEmbeddingError):
    pass


class InvalidEmbeddingError(FaceEmbeddingError):
    pass


class FaceEmbeddingPlugin:
    """Postprocess AlignedFace values into normalized vectors only."""

    def __init__(self, settings: Mapping[str, Any], model_manager: ModelManager) -> None:
        self.manager = model_manager
        self.alias = str(settings.get("model_alias", "face_embedding_default"))
        self.model_name = str(settings.get("model_name", "w600k_mbf"))
        self.model_version = str(settings.get("model_version", "buffalo_sc-v0.7"))
        self.model_path = Path(
            str(settings.get("model_path", "models/face_embedding/w600k_mbf.onnx"))
        )
        self.dimension = int(settings.get("embedding_dimension", 512))
        self.input_width = int(settings.get("input_width", 112))
        self.input_height = int(settings.get("input_height", 112))
        self.source_color = str(settings.get("source_color", "BGR")).upper()
        self.model_color = str(settings.get("model_color", "RGB")).upper()
        self.scale = float(settings.get("scale", 1.0))
        self.mean = _triple(settings.get("mean", [127.5, 127.5, 127.5]), "mean")
        self.std = _triple(settings.get("std", [127.5, 127.5, 127.5]), "std")
        self.layout = str(settings.get("layout", "NCHW")).upper()
        self._validate_settings()

        self.manager.register_loader(ModelBackend.ONNX_RUNTIME, OpenCVArcFaceModelLoader())
        spec = ModelSpec(
            self.model_name,
            self.model_version,
            ModelBackend.ONNX_RUNTIME,
            self.model_path,
            metadata={
                "input_size": (self.input_width, self.input_height),
                "source_color": self.source_color,
                "model_color": self.model_color,
                "scale": self.scale,
                "mean": self.mean,
                "std": self.std,
                "layout": self.layout,
                "embedding_dimension": self.dimension,
            },
        )
        if not self.manager.exists(spec.key):
            self.manager.register(spec)
        self.manager.set_alias(self.alias, spec.key)
        self._lock = threading.Lock()
        self._received = self._generated = self._skipped = self._errors = 0
        self._valid = self._low_quality = 0
        self._total_ms = 0.0
        self._model_load_ms = 0.0
        self._last_pre_normalization_norm: float | None = None

    def embed(self, aligned_faces: Sequence[AlignedFace]) -> tuple[FaceEmbedding, ...]:
        started = time.monotonic()
        received = len(aligned_faces)
        skipped = sum(face.status is AlignmentStatus.REJECTED for face in aligned_faces)
        processable = tuple(face for face in aligned_faces if face.status is AlignmentStatus.ALIGNED)
        generated: list[FaceEmbedding] = []
        try:
            if processable:
                loaded = self.manager.get_model_by_alias(self.alias)
                if not isinstance(loaded, LoadedArcFaceModel):
                    raise FaceEmbeddingError("unexpected model object")
                self._model_load_ms = loaded.load_time_ms
                for face in processable:
                    generated.append(self._embed_one(face, loaded))
        except Exception:
            with self._lock:
                self._received += received
                self._skipped += skipped
                self._errors += 1
                self._total_ms += (time.monotonic() - started) * 1_000
            raise
        elapsed = (time.monotonic() - started) * 1_000
        with self._lock:
            self._received += received
            self._skipped += skipped
            self._generated += len(generated)
            self._valid += sum(
                item.alignment_quality is AlignmentQuality.VALID for item in generated
            )
            self._low_quality += sum(
                item.alignment_quality is AlignmentQuality.LOW_QUALITY for item in generated
            )
            self._total_ms += elapsed
        return tuple(generated)

    def metrics(self) -> FaceEmbeddingMetrics:
        with self._lock:
            return FaceEmbeddingMetrics(
                self._received,
                self._generated,
                self._skipped,
                self._errors,
                self._model_load_ms,
                self._total_ms,
                self._total_ms / self._generated if self._generated else 0.0,
                self.dimension,
                self._valid,
                self._low_quality,
            )

    def release(self) -> None:
        self.manager.unload(self.manager.resolve_alias(self.alias))

    def _embed_one(self, face: AlignedFace, loaded: LoadedArcFaceModel) -> FaceEmbedding:
        if face.image is None:
            raise InvalidAlignedFaceError(f"face {face.face_index} has no aligned image")
        if face.image.shape != (self.input_height, self.input_width, 3):
            raise InvalidAlignedFaceError(
                f"face {face.face_index} image must be {self.input_width}x{self.input_height} BGR"
            )
        if face.image.dtype != np.uint8:
            raise InvalidAlignedFaceError(f"face {face.face_index} image must use uint8 BGR")
        inference_started = time.monotonic()
        blob = self._preprocess(face.image)
        loaded.network.setInput(blob)
        raw = np.asarray(loaded.network.forward(), dtype=np.float32).reshape(-1)
        if raw.size != self.dimension:
            raise InvalidEmbeddingError(
                f"expected embedding dimension {self.dimension}, got {raw.size}"
            )
        if not np.isfinite(raw).all():
            raise InvalidEmbeddingError("model output contains NaN or infinity")
        raw_norm = float(np.linalg.norm(raw))
        if not math.isfinite(raw_norm) or raw_norm <= 1e-12:
            raise InvalidEmbeddingError("model output has zero or invalid L2 norm")
        vector = np.asarray(raw / raw_norm, dtype=np.float32)
        norm = float(np.linalg.norm(vector))
        inference_ms = (time.monotonic() - inference_started) * 1_000
        # raw_norm is intentionally diagnostic-only and never exposed as identity data.
        self._last_pre_normalization_norm = raw_norm
        LOGGER.debug(
            "Pre-normalization embedding norm; run_id=%s face_index=%d norm=%.6f",
            face.run_id,
            face.face_index,
            raw_norm,
        )
        return FaceEmbedding(
            face.frame, face.run_id, face.face_index, vector, self.dimension, norm,
            face.quality, inference_ms, "opencv_dnn", self.model_name,
            self.model_version, loaded.weights_sha256,
        )

    def _preprocess(self, image: np.ndarray) -> np.ndarray:
        array = image.astype(np.float32, copy=True)
        if self.source_color != self.model_color:
            array = array[..., ::-1]
        array = (array - np.asarray(self.mean, dtype=np.float32))
        array = array / np.asarray(self.std, dtype=np.float32)
        array *= self.scale
        if self.layout == "NCHW":
            array = np.transpose(array, (2, 0, 1))
        return np.ascontiguousarray(array[None], dtype=np.float32)

    def _validate_settings(self) -> None:
        if self.dimension <= 0 or self.input_width <= 0 or self.input_height <= 0:
            raise ValueError("dimensions must be positive")
        if (self.input_width, self.input_height) != (112, 112):
            raise ValueError("the aligned-face input contract is fixed at 112x112")
        if self.source_color != "BGR":
            raise ValueError("AlignedFace source_color must be BGR")
        if self.model_color not in {"BGR", "RGB"}:
            raise ValueError("model_color must be BGR or RGB")
        if self.layout not in {"NCHW", "NHWC"}:
            raise ValueError("layout must be NCHW or NHWC")
        if not math.isfinite(self.scale):
            raise ValueError("scale must be finite")
        if any(not math.isfinite(value) or value <= 0 for value in self.std):
            raise ValueError("std values must be finite and positive")


def _triple(value: Any, name: str) -> tuple[float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"{name} must contain three values")
    result = tuple(float(item) for item in value)
    if not all(math.isfinite(item) for item in result):
        raise ValueError(f"{name} must contain finite values")
    return result  # type: ignore[return-value]
