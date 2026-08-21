"""Compatibility exports for Biometrics recognition domain contracts."""

from src.core.biometrics.domain.recognition import (
    RecognitionCandidate,
    RecognitionPolicy,
    RecognitionQuality,
    RecognitionResult,
    RecognitionState,
)

__all__ = [name for name in globals() if name.startswith("Recognition")]
