"""Typed contracts for guided face capture quality gates."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from src.engine.embedding.contracts import FaceEmbedding

if TYPE_CHECKING:
    from src.engine.face_quality.contracts import FaceQualityScore


class GuidedCaptureState(str, Enum):
    ACCEPTED = "accepted"
    NO_FACE = "no_face"
    MULTIPLE_FACES = "multiple_faces"
    FACE_TOO_SMALL = "face_too_small"
    FACE_OFF_CENTER = "face_off_center"
    LOW_DETECTION_CONFIDENCE = "low_detection_confidence"
    LOW_INTEROCULAR_DISTANCE = "low_interocular_distance"
    PARTIALLY_VISIBLE = "partially_visible"
    TOO_DARK = "too_dark"
    TOO_BRIGHT = "too_bright"
    LOW_CONTRAST = "low_contrast"
    BLURRY = "blurry"
    POSE_NOT_REQUESTED = "pose_not_requested"
    TOO_SOON = "too_soon"
    NEAR_DUPLICATE = "near_duplicate"
    ALIGNMENT_FAILED = "alignment_failed"
    EMBEDDING_FAILED = "embedding_failed"


class CapturePose(str, Enum):
    FRONTAL = "frontal"
    SLIGHT_LEFT = "slight_left"
    SLIGHT_RIGHT = "slight_right"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class GuidedCapturePolicy:
    min_detection_confidence: float
    min_relative_face_size: float
    min_interocular_distance: float
    min_visible_box_ratio: float
    max_center_offset_x: float
    max_center_offset_y: float
    min_blur_variance: float
    min_mean_illumination: float
    max_mean_illumination: float
    min_contrast: float
    frontal_max_yaw_ratio: float
    slight_turn_min_yaw_ratio: float
    slight_turn_max_yaw_ratio: float
    pose_ambiguity_tolerance: float
    min_sample_interval_seconds: float
    max_near_duplicate_similarity: float
    mirrored_source: bool = False

    def __post_init__(self) -> None:
        unit_values = (
            self.min_detection_confidence, self.min_relative_face_size,
            self.min_interocular_distance, self.min_visible_box_ratio,
            self.max_center_offset_x, self.max_center_offset_y,
        )
        if any(not math.isfinite(value) or not 0 <= value <= 1 for value in unit_values):
            raise ValueError("normalized guided-capture limits must be between 0 and 1")
        if not 0 <= self.min_mean_illumination < self.max_mean_illumination <= 255:
            raise ValueError("illumination limits must be ordered within 0..255")
        if any(not math.isfinite(value) or value < 0 for value in (
            self.min_blur_variance, self.min_contrast, self.frontal_max_yaw_ratio,
            self.slight_turn_min_yaw_ratio, self.slight_turn_max_yaw_ratio,
            self.pose_ambiguity_tolerance, self.min_sample_interval_seconds,
        )):
            raise ValueError("guided-capture limits must be finite and non-negative")
        if not self.frontal_max_yaw_ratio < self.slight_turn_min_yaw_ratio:
            raise ValueError("frontal and turned pose ranges must not overlap")
        if self.slight_turn_max_yaw_ratio < self.slight_turn_min_yaw_ratio:
            raise ValueError("slight turn limits are invalid")
        if not -1 <= self.max_near_duplicate_similarity <= 1:
            raise ValueError("near-duplicate similarity must be between -1 and 1")


@dataclass(frozen=True, slots=True)
class GuidedQualityMetrics:
    detection_confidence: float | None = None
    relative_face_size: float | None = None
    normalized_interocular_distance: float | None = None
    visible_box_ratio: float | None = None
    center_offset_x: float | None = None
    center_offset_y: float | None = None
    mean_illumination: float | None = None
    contrast: float | None = None
    blur_variance: float | None = None
    eye_nose_yaw_ratio: float | None = None
    mouth_nose_yaw_ratio: float | None = None
    checks_passed: int = 0
    checks_total: int = 0
    quality_score: float = 0.0


@dataclass(frozen=True, slots=True)
class GuidedCaptureResult:
    primary_state: GuidedCaptureState
    reasons: tuple[GuidedCaptureState, ...]
    accepted: bool
    visual_quality_passed: bool
    temporal_check_passed: bool
    diversity_check_passed: bool
    quality_metrics: GuidedQualityMetrics
    requested_pose: CapturePose
    estimated_pose: CapturePose
    face_index: int | None
    run_id: str
    timestamp: datetime
    embedding: FaceEmbedding | None = None
    face_quality_score: FaceQualityScore | None = None


@dataclass(frozen=True, slots=True)
class GuidedEvaluatorMetrics:
    frames_evaluated: int
    visually_valid_candidates: int
    visual_rejections: int
    temporal_rejections: int
    embeddings_calculated: int
    embedding_failures: int
    near_duplicate_rejections: int
    samples_accepted: int
