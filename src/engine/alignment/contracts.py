"""Typed contracts for five-point face alignment."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np

from src.camera.frame import Frame
from src.engine.contracts.detection import BoundingBox


class LandmarkOrder(str, Enum):
    """Required YuNet landmark order. The numeric value is the tuple index."""

    LEFT_EYE = "left_eye"
    RIGHT_EYE = "right_eye"
    NOSE = "nose"
    LEFT_MOUTH_CORNER = "left_mouth_corner"
    RIGHT_MOUTH_CORNER = "right_mouth_corner"


LANDMARK_ORDER: tuple[LandmarkOrder, ...] = (
    LandmarkOrder.LEFT_EYE,
    LandmarkOrder.RIGHT_EYE,
    LandmarkOrder.NOSE,
    LandmarkOrder.LEFT_MOUTH_CORNER,
    LandmarkOrder.RIGHT_MOUTH_CORNER,
)


class AlignmentStatus(str, Enum):
    ALIGNED = "aligned"
    REJECTED = "rejected"


class AlignmentQuality(str, Enum):
    VALID = "valid"
    LOW_QUALITY = "low_quality"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class AlignedFace:
    frame: Frame
    image: np.ndarray | None
    bounding_box: BoundingBox
    landmarks: tuple[tuple[float, float], ...]
    transform_matrix: np.ndarray | None
    inverse_transform_matrix: np.ndarray | None
    face_index: int
    confidence: float
    run_id: str
    status: AlignmentStatus
    quality: AlignmentQuality
    error: str | None
    alignment_time_ms: float
    normalized_interocular_distance: float
    relative_face_size: float
    visible_box_ratio: float


@dataclass(frozen=True, slots=True)
class AlignmentMetrics:
    faces_received: int
    faces_aligned: int
    faces_rejected: int
    valid_faces: int
    low_quality_faces: int
    total_alignment_time_ms: float
    average_alignment_time_ms: float
    output_width: int
    output_height: int
