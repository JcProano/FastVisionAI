"""Deterministic five-point similarity alignment using NumPy and OpenCV."""

from __future__ import annotations

import math
import threading
import time
from typing import Any, Sequence

import cv2
import numpy as np

from src.engine.alignment.contracts import (
    AlignedFace,
    AlignmentMetrics,
    AlignmentQuality,
    AlignmentStatus,
)
from src.engine.contracts.detection import BoundingBox, Detection, InferenceResult

TEMPLATE_VERSION = "fva-5pt-112-v1"
OUTPUT_SIZE = (112, 112)

# Fixed pixel coordinates in exact YuNet order: left eye, right eye, nose,
# left mouth corner, right mouth corner. Never mutate this array.
CANONICAL_LANDMARKS_112 = np.array(
    ((33.6, 39.2), (78.4, 39.2), (56.0, 61.6), (39.2, 84.0), (72.8, 84.0)),
    dtype=np.float64,
)
CANONICAL_LANDMARKS_112.setflags(write=False)


class FaceAlignmentError(ValueError):
    """Base error for invalid alignment inputs."""


class LandmarkCorrespondenceError(FaceAlignmentError):
    """Detection and landmark group counts do not correspond."""


class FaceAligner:
    """Align all detected faces while preserving rejected results and indices."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._received = self._aligned = self._rejected = 0
        self._valid = self._low_quality = 0
        self._total_ms = 0.0

    def align_result(self, result: InferenceResult) -> tuple[AlignedFace, ...]:
        attachments = result.attachments.get("face_detector", result.attachments)
        raw_landmarks = attachments.get("landmarks", ())
        run_id = str(attachments.get("run_id", ""))
        if len(result.detections) != len(raw_landmarks):
            raise LandmarkCorrespondenceError(
                f"detections={len(result.detections)} landmarks={len(raw_landmarks)}"
            )
        return self.align_faces(result.detections, raw_landmarks, result.frame, run_id)

    def align_faces(
        self,
        detections: Sequence[Detection],
        landmark_groups: Sequence[Sequence[Sequence[float]]],
        frame,
        run_id: str,
    ) -> tuple[AlignedFace, ...]:
        if len(detections) != len(landmark_groups):
            raise LandmarkCorrespondenceError(
                f"detections={len(detections)} landmarks={len(landmark_groups)}"
            )
        aligned = tuple(
            self._align_one(frame, detection, landmarks, index, run_id)
            for index, (detection, landmarks) in enumerate(zip(detections, landmark_groups))
        )
        with self._lock:
            self._received += len(aligned)
            self._aligned += sum(item.status is AlignmentStatus.ALIGNED for item in aligned)
            self._rejected += sum(item.status is AlignmentStatus.REJECTED for item in aligned)
            self._valid += sum(item.quality is AlignmentQuality.VALID for item in aligned)
            self._low_quality += sum(item.quality is AlignmentQuality.LOW_QUALITY for item in aligned)
            self._total_ms += sum(item.alignment_time_ms for item in aligned)
        return aligned

    def metrics(self) -> AlignmentMetrics:
        with self._lock:
            return AlignmentMetrics(
                faces_received=self._received,
                faces_aligned=self._aligned,
                faces_rejected=self._rejected,
                valid_faces=self._valid,
                low_quality_faces=self._low_quality,
                total_alignment_time_ms=self._total_ms,
                average_alignment_time_ms=(
                    self._total_ms / self._received if self._received else 0.0
                ),
                output_width=OUTPUT_SIZE[0],
                output_height=OUTPUT_SIZE[1],
            )

    def _align_one(
        self,
        frame,
        detection: Detection,
        landmarks: Sequence[Sequence[float]],
        face_index: int,
        run_id: str,
    ) -> AlignedFace:
        started = time.monotonic()
        normalized: tuple[tuple[float, float], ...] = ()
        interocular = relative_size = visible_ratio = 0.0
        try:
            normalized = _coerce_landmarks(landmarks)
            image = frame.image
            if image is None or getattr(image, "size", 0) == 0:
                raise FaceAlignmentError("empty_frame")
            height, width = image.shape[:2]
            box_pixels = _box_pixels(detection.bounding_box, width, height)
            relative_size, visible_ratio = _box_quality(box_pixels, width, height)
            if box_pixels[2] <= box_pixels[0] or box_pixels[3] <= box_pixels[1]:
                raise FaceAlignmentError("empty_box")
            source = np.array(
                [(x * width, y * height) for x, y in normalized], dtype=np.float64
            )
            _validate_landmark_order(source)
            interocular = float(np.linalg.norm(source[1] - source[0]) / math.hypot(width, height))
            matrix = _similarity_transform(source, CANONICAL_LANDMARKS_112)
            determinant = float(np.linalg.det(matrix[:, :2]))
            if not math.isfinite(determinant) or abs(determinant) < 1e-10:
                raise FaceAlignmentError("non_invertible_transform")
            inverse = cv2.invertAffineTransform(matrix)
            if not np.isfinite(inverse).all():
                raise FaceAlignmentError("non_invertible_transform")
            output = cv2.warpAffine(
                image,
                matrix,
                OUTPUT_SIZE,
                flags=cv2.INTER_LINEAR,
                borderMode=cv2.BORDER_CONSTANT,
                borderValue=(0, 0, 0),
            )
            quality = _quality(interocular, relative_size, visible_ratio)
            return AlignedFace(
                frame, output, detection.bounding_box, normalized, matrix, inverse,
                face_index, detection.confidence, run_id, AlignmentStatus.ALIGNED,
                quality, None, (time.monotonic() - started) * 1_000,
                interocular, relative_size, visible_ratio,
            )
        except (FaceAlignmentError, ValueError, TypeError, np.linalg.LinAlgError) as exc:
            return AlignedFace(
                frame, None, detection.bounding_box, normalized, None, None,
                face_index, detection.confidence, run_id, AlignmentStatus.REJECTED,
                AlignmentQuality.REJECTED, str(exc), (time.monotonic() - started) * 1_000,
                interocular, relative_size, visible_ratio,
            )


def _coerce_landmarks(landmarks: Sequence[Sequence[float]]) -> tuple[tuple[float, float], ...]:
    if len(landmarks) != 5:
        raise FaceAlignmentError("expected_five_landmarks")
    try:
        result = tuple((float(point[0]), float(point[1])) for point in landmarks)
    except (IndexError, TypeError, ValueError) as exc:
        raise FaceAlignmentError("invalid_landmark_shape") from exc
    if not all(math.isfinite(value) for point in result for value in point):
        raise FaceAlignmentError("non_finite_landmarks")
    return result


def _validate_landmark_order(points: np.ndarray) -> None:
    left_eye, right_eye, nose, left_mouth, right_mouth = points
    if left_eye[0] >= right_eye[0] or left_mouth[0] >= right_mouth[0]:
        raise FaceAlignmentError("invalid_landmark_order")
    eye_y = float((left_eye[1] + right_eye[1]) / 2)
    mouth_y = float((left_mouth[1] + right_mouth[1]) / 2)
    if not eye_y < nose[1] < mouth_y:
        raise FaceAlignmentError("invalid_landmark_order")
    if np.linalg.matrix_rank(points - points.mean(axis=0)) < 2:
        raise FaceAlignmentError("degenerate_landmarks")


def _similarity_transform(source: np.ndarray, target: np.ndarray) -> np.ndarray:
    source_mean = source.mean(axis=0)
    target_mean = target.mean(axis=0)
    source_centered = source - source_mean
    target_centered = target - target_mean
    variance = float(np.sum(source_centered ** 2) / len(source))
    if variance <= 1e-12:
        raise FaceAlignmentError("degenerate_landmarks")
    covariance = target_centered.T @ source_centered / len(source)
    u, singular, vt = np.linalg.svd(covariance)
    correction = np.eye(2)
    if np.linalg.det(u) * np.linalg.det(vt) < 0:
        correction[-1, -1] = -1
    rotation = u @ correction @ vt
    scale = float(np.sum(singular * np.diag(correction)) / variance)
    linear = scale * rotation
    translation = target_mean - linear @ source_mean
    matrix = np.column_stack((linear, translation)).astype(np.float64)
    if not np.isfinite(matrix).all():
        raise FaceAlignmentError("invalid_transform")
    return matrix


def _box_pixels(box: BoundingBox, width: int, height: int) -> tuple[float, float, float, float]:
    if box.normalized:
        return box.x1 * width, box.y1 * height, box.x2 * width, box.y2 * height
    return box.x1, box.y1, box.x2, box.y2


def _box_quality(box: tuple[float, float, float, float], width: int, height: int) -> tuple[float, float]:
    x1, y1, x2, y2 = box
    area = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    relative = area / (width * height)
    visible_width = max(0.0, min(float(width), x2) - max(0.0, x1))
    visible_height = max(0.0, min(float(height), y2) - max(0.0, y1))
    visible = visible_width * visible_height / area if area > 0 else 0.0
    return relative, min(1.0, visible)


def _quality(interocular: float, relative_size: float, visible_ratio: float) -> AlignmentQuality:
    if interocular < 0.025 or relative_size < 0.005 or visible_ratio < 0.75:
        return AlignmentQuality.LOW_QUALITY
    return AlignmentQuality.VALID
