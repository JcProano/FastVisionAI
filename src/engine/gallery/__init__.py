"""In-memory biometric gallery and score-only similarity matching."""

from src.engine.gallery.contracts import (
    FaceIdentity,
    FaceTemplate,
    MatchCandidate,
    MatchDecision,
    MatchPolicy,
    MatchQuery,
    MatchResult,
    ModelCompatibility,
)
from src.engine.gallery.gallery import (
    DuplicateIdentityError,
    DuplicateTemplateError,
    FaceGallery,
    GalleryCompatibilityError,
    IdentityNotFoundError,
)
from src.engine.gallery.matcher import FaceMatcher

__all__ = [
    "DuplicateIdentityError", "DuplicateTemplateError", "FaceGallery",
    "FaceIdentity", "FaceMatcher", "FaceTemplate", "GalleryCompatibilityError",
    "IdentityNotFoundError", "MatchCandidate", "MatchDecision", "MatchPolicy",
    "MatchQuery", "MatchResult", "ModelCompatibility",
]
