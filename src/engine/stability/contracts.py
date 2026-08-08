"""Scalar-only contracts for temporal observation stability.

``STABLE`` means temporal continuity only. It is never an identity, access,
recognition, attendance, or biometric decision.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


class StabilityValidationError(ValueError):
    pass


class StabilityState(str, Enum):
    NO_OBSERVATION = "NO_OBSERVATION"
    STABILIZING = "STABILIZING"
    STABLE = "STABLE"
    LOST = "LOST"
    CHANGED = "CHANGED"
    MULTIPLE_FACES = "MULTIPLE_FACES"
    INCOMPATIBLE = "INCOMPATIBLE"


@dataclass(frozen=True, slots=True)
class StabilityPolicy:
    enabled: bool = True
    minimum_observations: int = 5
    minimum_duration_seconds: float = 1.5
    maximum_gap_seconds: float = 0.75
    minimum_similarity: float | None = None
    reset_on_multiple_faces: bool = True
    reset_on_candidate_change: bool = True
    policy_name: str = "stability_development"
    policy_version: str = "1.0"

    def __post_init__(self) -> None:
        if self.minimum_observations <= 0:
            raise StabilityValidationError("minimum_observations must be positive")
        durations = (self.minimum_duration_seconds, self.maximum_gap_seconds)
        if any(not math.isfinite(value) or value < 0 for value in durations):
            raise StabilityValidationError("stability durations must be finite and non-negative")
        if self.minimum_similarity is not None and (
            not math.isfinite(self.minimum_similarity)
            or not -1.0 <= self.minimum_similarity <= 1.0
        ):
            raise StabilityValidationError("minimum_similarity must be within [-1, 1]")
        if not self.policy_name.strip() or not self.policy_version.strip():
            raise StabilityValidationError("stability policy provenance is required")


@dataclass(frozen=True, slots=True)
class StabilityObservation:
    timestamp_monotonic: float | None
    person_id: str | None
    recognition_state: str
    similarity: float | None
    face_count: int
    quality_score: float | None
    run_id: str

    def __post_init__(self) -> None:
        if self.timestamp_monotonic is not None and (
            not math.isfinite(self.timestamp_monotonic) or self.timestamp_monotonic < 0
        ):
            raise StabilityValidationError("monotonic timestamp is invalid")
        if self.face_count < 0:
            raise StabilityValidationError("face_count cannot be negative")
        if self.person_id is not None and not self.person_id.strip():
            raise StabilityValidationError("person_id cannot be blank")
        for name, value in (("similarity", self.similarity), ("quality_score", self.quality_score)):
            if value is not None and not math.isfinite(value):
                raise StabilityValidationError(f"{name} must be finite")
        if self.similarity is not None and not -1.0 <= self.similarity <= 1.0:
            raise StabilityValidationError("similarity must be within [-1, 1]")
        if not self.recognition_state.strip() or not self.run_id.strip():
            raise StabilityValidationError("recognition_state and run_id are required")


@dataclass(frozen=True, slots=True)
class StabilityResult:
    state: StabilityState
    person_id: str | None
    observations_count: int
    stable_duration_seconds: float
    current_similarity: float | None
    average_similarity: float | None
    minimum_similarity: float | None
    maximum_similarity: float | None
    first_seen_monotonic: float | None
    last_seen_monotonic: float | None
    reason: str
    policy_name: str
    policy_version: str
