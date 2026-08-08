"""Structured, policy-controlled interpretation of face similarity results."""

from .contracts import (
    RecognitionCandidate, RecognitionPolicy, RecognitionQuality, RecognitionResult,
    RecognitionState,
)
from .service import RecognitionService

__all__ = [
    "RecognitionCandidate", "RecognitionPolicy", "RecognitionQuality",
    "RecognitionResult", "RecognitionService", "RecognitionState",
]
