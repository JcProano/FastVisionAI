"""Typed outputs and metrics for face embedding generation."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from src.camera.frame import Frame
from src.engine.alignment.contracts import AlignmentQuality


@dataclass(frozen=True, slots=True)
class FaceEmbedding:
    frame: Frame
    run_id: str
    face_index: int
    embedding: np.ndarray
    dimension: int
    l2_norm: float
    alignment_quality: AlignmentQuality
    inference_time_ms: float
    backend: str
    model: str
    version: str
    weights_sha256: str

    def __post_init__(self) -> None:
        vector = self.embedding
        if not isinstance(vector, np.ndarray) or vector.dtype != np.float32 or vector.ndim != 1:
            raise ValueError("embedding must be a one-dimensional float32 NumPy array")
        if self.dimension <= 0 or vector.size != self.dimension:
            raise ValueError("embedding dimension does not match vector size")
        if not np.isfinite(vector).all():
            raise ValueError("embedding must contain only finite values")
        if not math.isfinite(self.l2_norm) or not math.isclose(self.l2_norm, 1.0, abs_tol=1e-5):
            raise ValueError("embedding must be L2-normalized")
        if not self.weights_sha256:
            raise ValueError("weights_sha256 is required")
        vector.setflags(write=False)


@dataclass(frozen=True, slots=True)
class FaceEmbeddingMetrics:
    faces_received: int
    embeddings_generated: int
    faces_skipped: int
    errors: int
    model_load_time_ms: float
    total_time_ms: float
    average_time_per_face_ms: float
    embedding_dimension: int
    valid_quality_embeddings: int
    low_quality_embeddings: int
