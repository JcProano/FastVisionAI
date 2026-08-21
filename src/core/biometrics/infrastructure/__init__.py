"""Adapters for numerical and legacy biometric engine concerns."""

from .engine_identity_factory import EngineFaceIdentityFactory
from .gallery_persistence import (
    GalleryPersistence,
    GalleryPersistenceError,
    ImportLimits,
    PersistenceDisabledError,
    SCHEMA_VERSION,
)
from .numpy_calibration_analyzer import NumpyCalibrationAnalyzer
from .numpy_embedding_math import NumpyEmbeddingMath

__all__ = [
    "EngineFaceIdentityFactory",
    "GalleryPersistence",
    "GalleryPersistenceError",
    "ImportLimits",
    "NumpyCalibrationAnalyzer",
    "NumpyEmbeddingMath",
    "PersistenceDisabledError",
    "SCHEMA_VERSION",
]
