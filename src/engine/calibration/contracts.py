"""Typed contracts for biometric similarity calibration."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from src.engine.alignment.contracts import AlignmentQuality


class CalibrationWarning(str, Enum):
    SINGLE_SESSION = "single_session"
    FEW_IDENTITIES = "few_identities"
    FEW_GENUINE_PAIRS = "few_genuine_pairs"
    FEW_IMPOSTOR_PAIRS = "few_impostor_pairs"
    LOW_QUALITY_PREDOMINATES = "low_quality_predominates"
    HOMOGENEOUS_CAPTURE_CONDITIONS = "homogeneous_capture_conditions"


class CalibrationSampleType(str, Enum):
    GENUINE = "GENUINE"
    IMPOSTOR = "IMPOSTOR"


class CalibrationIllumination(str, Enum):
    NORMAL = "NORMAL"
    LOW = "LOW"
    SIDE = "SIDE"


class CalibrationDistance(str, Enum):
    NEAR = "NEAR"
    OPERATIONAL = "OPERATIONAL"
    FAR = "FAR"


class CalibrationPose(str, Enum):
    FRONTAL = "FRONTAL"
    SLIGHT_LEFT = "SLIGHT_LEFT"
    SLIGHT_RIGHT = "SLIGHT_RIGHT"


@dataclass(frozen=True, slots=True)
class CalibrationPolicy:
    min_identities: int = 2
    min_samples_per_identity: int = 2
    percentiles: tuple[float, ...] = (1.0, 5.0, 25.0, 50.0, 75.0, 95.0, 99.0)
    histogram_bins: int = 20
    warning_min_identities: int = 5
    warning_min_genuine_pairs: int = 20
    warning_min_impostor_pairs: int = 100
    max_impostor_pairs: int | None = None
    impostor_sampling_seed: int = 0

    def __post_init__(self) -> None:
        if self.min_identities < 2 or self.min_samples_per_identity < 2:
            raise ValueError("calibration requires at least two identities and two samples each")
        if self.histogram_bins <= 0:
            raise ValueError("histogram_bins must be positive")
        if self.max_impostor_pairs is not None and self.max_impostor_pairs <= 0:
            raise ValueError("max_impostor_pairs must be positive when configured")
        if any(not math.isfinite(item) or not 0 <= item <= 100 for item in self.percentiles):
            raise ValueError("percentiles must be finite and between 0 and 100")


@dataclass(frozen=True, slots=True)
class CalibrationSampleMetadata:
    session_id: str
    temporary_identity_id: str
    captured_at: datetime
    source_identifier: str
    resolution: tuple[int, int]
    alignment_quality: AlignmentQuality
    model: str
    version: str
    weights_sha256: str
    face_quality_score: float | None = None
    face_quality_band: str | None = None
    quality_profile_name: str | None = None
    quality_profile_version: str | None = None
    sample_type: CalibrationSampleType | None = None
    expected_identity: str | None = None
    calibration_session_id: str | None = None
    evaluation_sample_id: str | None = None
    condition_id: str | None = None
    illumination: CalibrationIllumination | None = None
    distance: CalibrationDistance | None = None
    pose: CalibrationPose | None = None

    def __post_init__(self) -> None:
        if not all((self.session_id, self.temporary_identity_id, self.source_identifier,
                    self.model, self.version, self.weights_sha256)):
            raise ValueError("calibration metadata fields must be non-empty")
        if self.captured_at.tzinfo is None:
            raise ValueError("captured_at must be timezone-aware UTC")
        if self.captured_at.utcoffset() is None or self.captured_at.utcoffset().total_seconds() != 0:
            raise ValueError("captured_at must use UTC")
        if self.resolution[0] <= 0 or self.resolution[1] <= 0:
            raise ValueError("resolution must be positive")
        if self.alignment_quality is AlignmentQuality.REJECTED:
            raise ValueError("rejected samples cannot be calibrated")
        if self.face_quality_score is not None and (
            not math.isfinite(self.face_quality_score) or not 0 <= self.face_quality_score <= 100
        ):
            raise ValueError("face_quality_score must be finite and within 0..100")
        identifiers = (
            self.calibration_session_id, self.evaluation_sample_id, self.condition_id,
        )
        if any(value is not None for value in identifiers) and not all(identifiers):
            raise ValueError("RC17 calibration identifiers must be provided together")
        if self.sample_type is CalibrationSampleType.GENUINE and not self.expected_identity:
            raise ValueError("genuine evaluation requires expected_identity")
        if self.sample_type is CalibrationSampleType.IMPOSTOR and self.expected_identity is not None:
            raise ValueError("impostor evaluation cannot have expected_identity")


@dataclass(frozen=True, slots=True)
class CalibrationSample:
    embedding: object
    metadata: CalibrationSampleMetadata


@dataclass(frozen=True, slots=True)
class DistributionStatistics:
    pair_count: int
    minimum: float
    mean: float
    median: float
    maximum: float
    standard_deviation: float
    percentiles: tuple[tuple[float, float], ...]
    histogram_edges: tuple[float, ...]
    histogram_counts: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class ThresholdRates:
    threshold: float
    impostors_accepted: int
    total_impostor_pairs: int
    far: float
    genuine_rejected: int
    total_genuine_pairs: int
    frr: float


@dataclass(frozen=True, slots=True)
class EstimatedEER:
    estimated: bool
    threshold: float
    far: float
    frr: float
    eer: float
    absolute_gap: float
    method: str


@dataclass(frozen=True, slots=True)
class CalibrationQualitySummary:
    valid_samples: int
    low_quality_samples: int
    genuine_pairs_with_low_quality: int
    impostor_pairs_with_low_quality: int


@dataclass(frozen=True, slots=True)
class CalibrationReport:
    model: str
    version: str
    weights_sha256: str
    embedding_dimension: int
    identity_count: int
    templates_per_identity: tuple[tuple[str, int], ...]
    quality: CalibrationQualitySummary
    genuine_distribution: DistributionStatistics
    impostor_distribution: DistributionStatistics
    total_possible_impostor_pairs: int
    used_impostor_pairs: int
    impostor_pairs_sampled: bool
    threshold_rates: tuple[ThresholdRates, ...]
    estimated_eer: EstimatedEER
    warnings: tuple[CalibrationWarning, ...]
    generated_at: datetime
    run_id: str
    synthetic_validation: bool
