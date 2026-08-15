"""Ordered visual, temporal and diversity evaluation for guided capture.

Evaluation order is fixed: face count; alignment; confidence; size/interocular/
visibility; centering; illumination/contrast/blur; requested pose; time; embedding;
and finally similarity against previously accepted samples.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from datetime import datetime, timezone

import cv2
import numpy as np

from src.engine.alignment.contracts import AlignedFace, AlignmentStatus
from src.engine.capture_quality.contracts import (
    CapturePose, GuidedCapturePolicy, GuidedCaptureResult, GuidedCaptureState,
    GuidedEvaluatorMetrics, GuidedQualityMetrics,
)
from src.engine.contracts.detection import Detection
from src.engine.embedding.contracts import FaceEmbedding

EmbeddingProvider = Callable[[AlignedFace], FaceEmbedding]


class FaceCaptureQualityEvaluator:
    """Stateful evaluator that remembers accepted timestamps, frames and vectors."""

    def __init__(self, policy: GuidedCapturePolicy) -> None:
        self.policy = policy
        self._accepted: list[FaceEmbedding] = []
        self._accepted_records: list[tuple[FaceEmbedding, tuple[str, int, int],
                                           tuple[str, int, float], float]] = []
        self._accepted_sequences: set[tuple[str, int, int]] = set()
        self._accepted_timestamps: set[tuple[str, int, float]] = set()
        self._last_accepted_timestamp: float | None = None
        self._lock = threading.Lock()
        self._frames = self._visual_valid = self._visual_rejected = 0
        self._temporal_rejected = self._embeddings = self._embedding_failures = 0
        self._duplicates = self._accepted_count = 0

    def evaluate(
        self,
        detections: Sequence[Detection],
        aligned_faces: Sequence[AlignedFace],
        requested_pose: CapturePose,
        run_id: str,
        captured_monotonic: float,
        embedding_provider: EmbeddingProvider,
        *,
        timestamp: datetime | None = None,
    ) -> GuidedCaptureResult:
        timestamp = timestamp or datetime.now(timezone.utc)
        with self._lock:
            self._frames += 1
        if len(detections) != 1:
            state = (GuidedCaptureState.NO_FACE if not detections
                     else GuidedCaptureState.MULTIPLE_FACES)
            return self._visual_failure((state,), requested_pose, run_id, timestamp)
        if (len(aligned_faces) != 1 or aligned_faces[0].status is not AlignmentStatus.ALIGNED
                or aligned_faces[0].image is None):
            return self._visual_failure(
                (GuidedCaptureState.ALIGNMENT_FAILED,), requested_pose, run_id, timestamp
            )

        face = aligned_faces[0]
        estimated_pose, eye_ratio, mouth_ratio = self._estimate_pose(face.landmarks)
        image_metrics = _image_metrics(face.image)
        center_x = abs((face.bounding_box.x1 + face.bounding_box.x2) / 2 - .5)
        center_y = abs((face.bounding_box.y1 + face.bounding_box.y2) / 2 - .5)
        ordered_checks = (
            (face.confidence >= self.policy.min_detection_confidence,
             GuidedCaptureState.LOW_DETECTION_CONFIDENCE),
            (face.relative_face_size >= self.policy.min_relative_face_size,
             GuidedCaptureState.FACE_TOO_SMALL),
            (face.normalized_interocular_distance >= self.policy.min_interocular_distance,
             GuidedCaptureState.LOW_INTEROCULAR_DISTANCE),
            (face.visible_box_ratio >= self.policy.min_visible_box_ratio,
             GuidedCaptureState.PARTIALLY_VISIBLE),
            (center_x <= self.policy.max_center_offset_x and
             center_y <= self.policy.max_center_offset_y, GuidedCaptureState.FACE_OFF_CENTER),
            (image_metrics[0] >= self.policy.min_mean_illumination,
             GuidedCaptureState.TOO_DARK),
            (image_metrics[0] <= self.policy.max_mean_illumination,
             GuidedCaptureState.TOO_BRIGHT),
            (image_metrics[1] >= self.policy.min_contrast, GuidedCaptureState.LOW_CONTRAST),
            (image_metrics[2] >= self.policy.min_blur_variance, GuidedCaptureState.BLURRY),
            (estimated_pose is requested_pose, GuidedCaptureState.POSE_NOT_REQUESTED),
        )
        reasons = tuple(reason for passed, reason in ordered_checks if not passed)
        passed = sum(item[0] for item in ordered_checks)
        quality = GuidedQualityMetrics(
            face.confidence, face.relative_face_size, face.normalized_interocular_distance,
            face.visible_box_ratio, center_x, center_y, *image_metrics, eye_ratio, mouth_ratio,
            passed, len(ordered_checks), passed / len(ordered_checks),
        )
        if reasons:
            with self._lock:
                self._visual_rejected += 1
            return _result(reasons, False, False, False, quality, requested_pose,
                           estimated_pose, face.face_index, run_id, timestamp)
        with self._lock:
            self._visual_valid += 1
            sequence_key, timestamp_key = _frame_keys(face)
            temporal_ok = (
                sequence_key not in self._accepted_sequences and
                timestamp_key not in self._accepted_timestamps and
                (self._last_accepted_timestamp is None or captured_monotonic -
                 self._last_accepted_timestamp >= self.policy.min_sample_interval_seconds)
            )
            if not temporal_ok:
                self._temporal_rejected += 1
        if not temporal_ok:
            return _result((GuidedCaptureState.TOO_SOON,), True, False, False, quality,
                           requested_pose, estimated_pose, face.face_index, run_id, timestamp)
        try:
            embedding = embedding_provider(face)
            if embedding.frame is not face.frame or embedding.run_id != run_id:
                raise ValueError("embedding provenance mismatch")
        except Exception:
            with self._lock:
                self._embedding_failures += 1
            return _result((GuidedCaptureState.EMBEDDING_FAILED,), True, True, False, quality,
                           requested_pose, estimated_pose, face.face_index, run_id, timestamp)
        with self._lock:
            self._embeddings += 1
            near_duplicate = any(
                _cosine(embedding.embedding, accepted.embedding) >=
                self.policy.max_near_duplicate_similarity for accepted in self._accepted
            )
            if near_duplicate:
                self._duplicates += 1
            else:
                self._accepted.append(embedding)
                sequence_key, timestamp_key = _frame_keys(face)
                self._accepted_records.append(
                    (embedding, sequence_key, timestamp_key, captured_monotonic)
                )
                self._accepted_sequences.add(sequence_key)
                self._accepted_timestamps.add(timestamp_key)
                self._last_accepted_timestamp = captured_monotonic
                self._accepted_count += 1
        if near_duplicate:
            return _result((GuidedCaptureState.NEAR_DUPLICATE,), True, True, False, quality,
                           requested_pose, estimated_pose, face.face_index, run_id, timestamp)
        return _result((GuidedCaptureState.ACCEPTED,), True, True, True, quality,
                       requested_pose, estimated_pose, face.face_index, run_id, timestamp,
                       embedding)

    def reject_last_accepted(self, result: GuidedCaptureResult) -> bool:
        """Undo a tentative acceptance rejected by the enrollment score gate."""
        embedding = result.embedding
        with self._lock:
            if embedding is None or not self._accepted_records:
                return False
            accepted, sequence_key, timestamp_key, _captured = self._accepted_records[-1]
            if accepted is not embedding:
                return False
            self._accepted_records.pop(); self._accepted.pop()
            self._accepted_sequences.discard(sequence_key)
            self._accepted_timestamps.discard(timestamp_key)
            self._last_accepted_timestamp = (
                None if not self._accepted_records else self._accepted_records[-1][3]
            )
            self._accepted_count -= 1
            return True

    def restore_accepted(self, result: GuidedCaptureResult) -> bool:
        """Commit one previously rejected tentative result after UI stability."""
        embedding = result.embedding
        if embedding is None:
            return False
        sequence_key, timestamp_key = _frame_keys_from_embedding(embedding)
        captured_monotonic = embedding.frame.monotonic_timestamp
        with self._lock:
            if sequence_key in self._accepted_sequences:
                return False
            self._accepted.append(embedding)
            self._accepted_records.append(
                (embedding, sequence_key, timestamp_key, captured_monotonic)
            )
            self._accepted_sequences.add(sequence_key)
            self._accepted_timestamps.add(timestamp_key)
            self._last_accepted_timestamp = captured_monotonic
            self._accepted_count += 1
            return True

    def metrics(self) -> GuidedEvaluatorMetrics:
        with self._lock:
            return GuidedEvaluatorMetrics(
                self._frames, self._visual_valid, self._visual_rejected,
                self._temporal_rejected, self._embeddings, self._embedding_failures,
                self._duplicates, self._accepted_count,
            )

    def _visual_failure(self, reasons, requested_pose, run_id, timestamp):
        with self._lock:
            self._visual_rejected += 1
        return _result(reasons, False, False, False, GuidedQualityMetrics(),
                       requested_pose, CapturePose.UNKNOWN, None, run_id, timestamp)

    def _estimate_pose(self, landmarks):
        if len(landmarks) != 5:
            return CapturePose.UNKNOWN, None, None
        points = np.asarray(landmarks, dtype=np.float64)
        if not np.isfinite(points).all():
            return CapturePose.UNKNOWN, None, None
        left_eye, right_eye, nose, left_mouth, right_mouth = points
        eye_distance = float(np.linalg.norm(right_eye - left_eye))
        if eye_distance <= 1e-9:
            return CapturePose.UNKNOWN, None, None
        eye_ratio = float((nose[0] - (left_eye[0] + right_eye[0]) / 2) / eye_distance)
        mouth_ratio = float((nose[0] - (left_mouth[0] + right_mouth[0]) / 2) / eye_distance)
        if self.policy.mirrored_source:
            eye_ratio, mouth_ratio = -eye_ratio, -mouth_ratio
        if abs(eye_ratio - mouth_ratio) > self.policy.pose_ambiguity_tolerance:
            return CapturePose.UNKNOWN, eye_ratio, mouth_ratio
        magnitude = max(abs(eye_ratio), abs(mouth_ratio))
        if magnitude <= self.policy.frontal_max_yaw_ratio:
            return CapturePose.FRONTAL, eye_ratio, mouth_ratio
        if not self.policy.slight_turn_min_yaw_ratio <= magnitude <= self.policy.slight_turn_max_yaw_ratio:
            return CapturePose.UNKNOWN, eye_ratio, mouth_ratio
        if eye_ratio * mouth_ratio <= 0:
            return CapturePose.UNKNOWN, eye_ratio, mouth_ratio
        pose = CapturePose.SLIGHT_RIGHT if eye_ratio > 0 else CapturePose.SLIGHT_LEFT
        return pose, eye_ratio, mouth_ratio


def _image_metrics(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return float(gray.mean()), float(gray.std()), float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _cosine(left, right):
    return float(np.clip(np.dot(left, right), -1.0, 1.0))


def _frame_keys(face):
    frame = face.frame
    prefix = frame.source_name, frame.connection_id
    return (*prefix, frame.sequence_id), (*prefix, frame.monotonic_timestamp)


def _frame_keys_from_embedding(embedding: FaceEmbedding):
    frame = embedding.frame
    prefix = frame.source_name, frame.connection_id
    return (*prefix, frame.sequence_id), (*prefix, frame.monotonic_timestamp)


def _result(reasons, visual, temporal, diversity, quality, requested, estimated,
            face_index, run_id, timestamp, embedding=None):
    primary = reasons[0]
    accepted = primary is GuidedCaptureState.ACCEPTED
    return GuidedCaptureResult(primary, tuple(reasons), accepted, visual, temporal, diversity,
                               quality, requested, estimated, face_index, run_id, timestamp,
                               embedding if accepted else None)
