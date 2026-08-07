"""Typed enrollment policy, decisions and metrics."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from src.engine.alignment.contracts import AlignmentQuality
from src.engine.gallery.contracts import FaceIdentity


class EnrollmentStatus(str, Enum):
    ENROLLED = "enrolled"
    REJECTED = "rejected"


class EnrollmentCause(str, Enum):
    IDENTITY_ALREADY_EXISTS = "identity_already_exists"
    LOW_QUALITY = "low_quality"
    INCOMPATIBLE_DIMENSION = "incompatible_dimension"
    INCOMPATIBLE_MODEL = "incompatible_model"
    INCOMPATIBLE_VERSION = "incompatible_version"
    INCOMPATIBLE_WEIGHTS = "incompatible_weights"
    EXACT_DUPLICATE = "exact_duplicate"
    INSUFFICIENT_DIVERSITY = "insufficient_diversity"
    INSUFFICIENT_SIMILARITY = "insufficient_similarity"
    MAX_TEMPLATES_EXCEEDED = "max_templates_exceeded"
    INSUFFICIENT_ACCEPTED_TEMPLATES = "insufficient_accepted_templates"
    GALLERY_CONFLICT = "gallery_conflict"
    TRANSACTION_FAILED = "transaction_failed"
    ROLLBACK_FAILED = "rollback_failed"


@dataclass(frozen=True, slots=True)
class EnrollmentPolicy:
    min_templates: int = 3
    max_templates: int = 5
    allow_low_quality: bool = False
    # Minimum consistency between captures of the same enrollment. None disables it.
    min_pairwise_similarity: float | None = None
    # Maximum similarity to prevent near-identical, non-diverse captures. None disables it.
    max_pairwise_similarity: float | None = None
    reject_exact_duplicates: bool = True

    def __post_init__(self) -> None:
        if self.min_templates <= 0 or self.max_templates < self.min_templates:
            raise ValueError("template limits are invalid")
        for value in (self.min_pairwise_similarity, self.max_pairwise_similarity):
            if value is not None and (not math.isfinite(value) or not -1.0 <= value <= 1.0):
                raise ValueError("pairwise similarities must be finite and between -1 and 1")
        if (
            self.min_pairwise_similarity is not None
            and self.max_pairwise_similarity is not None
            and self.min_pairwise_similarity > self.max_pairwise_similarity
        ):
            raise ValueError("minimum pairwise similarity cannot exceed maximum")


@dataclass(frozen=True, slots=True)
class AcceptedEnrollmentTemplate:
    input_index: int
    face_index: int
    quality: AlignmentQuality
    gallery_template_index: int | None
    face_quality_score: float | None = None
    quality_profile_name: str | None = None
    quality_profile_version: str | None = None


@dataclass(frozen=True, slots=True)
class RejectedEnrollmentTemplate:
    input_index: int
    face_index: int
    causes: tuple[EnrollmentCause, ...]


@dataclass(frozen=True, slots=True)
class EnrollmentMetrics:
    templates_received: int
    templates_accepted: int
    templates_rejected: int
    low_quality_rejected: int
    exact_duplicates_rejected: int
    incompatible_rejected: int
    diversity_rejected: int
    max_limit_rejected: int
    pairwise_comparisons: int
    minimum_pairwise_similarity: float | None
    average_pairwise_similarity: float | None
    maximum_pairwise_similarity: float | None
    elapsed_ms: float


@dataclass(frozen=True, slots=True)
class EnrollmentResult:
    identity: FaceIdentity
    accepted_templates: tuple[AcceptedEnrollmentTemplate, ...]
    rejected_templates: tuple[RejectedEnrollmentTemplate, ...]
    causes: tuple[EnrollmentCause, ...]
    status: EnrollmentStatus
    metrics: EnrollmentMetrics
