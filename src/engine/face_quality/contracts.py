"""Typed configuration and output contracts for continuous face quality."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Mapping


class QualityBand(str, Enum):
    EXCELLENT = "excellent"
    GOOD = "good"
    ACCEPTABLE = "acceptable"
    POOR = "poor"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class FaceQualityWeights:
    detection: float
    size: float
    interocular: float
    visibility: float
    centering: float
    sharpness: float
    illumination: float
    contrast: float
    pose: float

    def values(self) -> tuple[float, ...]:
        return (
            self.detection, self.size, self.interocular, self.visibility,
            self.centering, self.sharpness, self.illumination, self.contrast, self.pose,
        )


@dataclass(frozen=True, slots=True)
class HigherIsBetterLimit:
    minimum: float
    full_score: float

    def __post_init__(self) -> None:
        if not all(math.isfinite(value) for value in (self.minimum, self.full_score)):
            raise ValueError("normalization limits must be finite")
        if self.full_score <= self.minimum:
            raise ValueError("full_score must be greater than minimum")


@dataclass(frozen=True, slots=True)
class CenteringLimit:
    ideal_offset: float
    maximum_offset: float

    def __post_init__(self) -> None:
        if not 0 <= self.ideal_offset < self.maximum_offset:
            raise ValueError("centering limits must be ordered and non-negative")


@dataclass(frozen=True, slots=True)
class IlluminationLimit:
    absolute_minimum: float
    ideal_minimum: float
    ideal_maximum: float
    absolute_maximum: float

    def __post_init__(self) -> None:
        values = (self.absolute_minimum, self.ideal_minimum,
                  self.ideal_maximum, self.absolute_maximum)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("illumination limits must be finite")
        if not 0 <= values[0] < values[1] <= values[2] < values[3] <= 255:
            raise ValueError("illumination limits must be ordered within 0..255")


@dataclass(frozen=True, slots=True)
class PoseScores:
    requested_match: float
    requested_mismatch: float
    unknown: float

    def __post_init__(self) -> None:
        if any(not math.isfinite(value) or not 0 <= value <= 1
               for value in (self.requested_match, self.requested_mismatch, self.unknown)):
            raise ValueError("pose scores must be within 0..1")


@dataclass(frozen=True, slots=True)
class QualityBandThresholds:
    excellent: float
    good: float
    acceptable: float

    def __post_init__(self) -> None:
        if not 0 <= self.acceptable < self.good < self.excellent <= 100:
            raise ValueError("quality band thresholds must be strictly ordered")


@dataclass(frozen=True, slots=True)
class FaceQualityScoringProfile:
    profile_name: str
    profile_version: str
    weights: FaceQualityWeights
    detection: HigherIsBetterLimit
    size: HigherIsBetterLimit
    interocular: HigherIsBetterLimit
    visibility: HigherIsBetterLimit
    centering: CenteringLimit
    sharpness: HigherIsBetterLimit
    illumination: IlluminationLimit
    contrast: HigherIsBetterLimit
    pose: PoseScores
    bands: QualityBandThresholds
    critical_penalties: Mapping[str, float]
    structural_invalid_states: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.profile_name.strip() or not self.profile_version.strip():
            raise ValueError("quality profile name and version are required")
        weights = self.weights.values()
        if any(not math.isfinite(value) or value < 0 for value in weights):
            raise ValueError("quality weights must be finite and non-negative")
        if not math.isclose(math.fsum(weights), 1.0, rel_tol=0.0, abs_tol=1e-12):
            raise ValueError("quality weights must sum exactly to 1.0 within 1e-12")
        penalties = dict(self.critical_penalties)
        if any(not isinstance(key, str) or not key or not math.isfinite(value)
               or not 0 <= value <= 1 for key, value in penalties.items()):
            raise ValueError("critical penalties must map state names to values within 0..1")
        if not self.structural_invalid_states or any(not item for item in self.structural_invalid_states):
            raise ValueError("structural_invalid_states must be non-empty")
        object.__setattr__(self, "critical_penalties", MappingProxyType(penalties))


@dataclass(frozen=True, slots=True)
class FaceQualityScore:
    total_score: float
    detection_score: float
    size_score: float
    interocular_score: float
    visibility_score: float
    centering_score: float
    sharpness_score: float
    illumination_score: float
    contrast_score: float
    pose_score: float
    quality_band: QualityBand
    profile_name: str
    profile_version: str
    explanations: tuple[str, ...]
    run_id: str
    face_index: int | None

    def __post_init__(self) -> None:
        scores = (
            self.total_score, self.detection_score, self.size_score,
            self.interocular_score, self.visibility_score, self.centering_score,
            self.sharpness_score, self.illumination_score, self.contrast_score,
            self.pose_score,
        )
        if any(not math.isfinite(value) or not 0 <= value <= 100 for value in scores):
            raise ValueError("all face quality scores must be finite and within 0..100")

