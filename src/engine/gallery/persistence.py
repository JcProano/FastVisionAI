"""Compatibility exports for Biometrics gallery persistence infrastructure."""

from src.core.biometrics.infrastructure.gallery_persistence import (
    GalleryPersistence,
    GalleryPersistenceError,
    ImportLimits,
    PersistenceDisabledError,
    SCHEMA_VERSION,
)

__all__ = [
    "GalleryPersistence",
    "GalleryPersistenceError",
    "ImportLimits",
    "PersistenceDisabledError",
    "SCHEMA_VERSION",
]
