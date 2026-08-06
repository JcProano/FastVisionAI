"""Post-alignment face embedding; separate from the frame inference scheduler."""

from src.engine.embedding.contracts import FaceEmbedding, FaceEmbeddingMetrics
from src.engine.embedding.plugin import (
    FaceEmbeddingError,
    FaceEmbeddingPlugin,
    InvalidAlignedFaceError,
    InvalidEmbeddingError,
)

__all__ = [
    "FaceEmbedding",
    "FaceEmbeddingError",
    "FaceEmbeddingMetrics",
    "FaceEmbeddingPlugin",
    "InvalidAlignedFaceError",
    "InvalidEmbeddingError",
]
