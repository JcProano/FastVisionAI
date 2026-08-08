"""Safe aggregate diagnostics for a Guided Face Capture execution."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

import numpy as np

from src.engine.capture_quality.contracts import (
    CapturePose, GuidedCapturePolicy, GuidedCaptureResult,
)

PERCENTILES = (5.0, 25.0, 50.0, 75.0, 95.0)
COHORTS = ("accepted", "visually_valid", "rejected")


@dataclass(frozen=True, slots=True)
class NumericDistribution:
    count: int
    minimum: float | None
    mean: float | None
    median: float | None
    maximum: float | None
    percentiles: tuple[tuple[float, float], ...]


@dataclass(frozen=True, slots=True)
class MetricDiagnostic:
    metric: str
    current_limit: Any
    accepted: NumericDistribution
    visually_valid: NumericDistribution
    rejected: NumericDistribution


@dataclass(frozen=True, slots=True)
class RejectionControlDiagnostic:
    control: str
    occurrences: int
    percentage_of_rejected_frames: float


@dataclass(frozen=True, slots=True)
class PoseDiagnostic:
    evaluable_frames: int
    current_limits: dict[str, float]
    requested_counts: tuple[tuple[str, int], ...]
    estimated_counts: tuple[tuple[str, int], ...]
    confusion_matrix: tuple[tuple[str, tuple[tuple[str, int], ...]], ...]
    unknown_percentage: float
    match_percentage: float


@dataclass(frozen=True, slots=True)
class InterocularDiagnostic:
    current_minimum: float
    available_frames: int
    below_limit_frames: int
    below_limit_percentage: float
    distribution: NumericDistribution


@dataclass(frozen=True, slots=True)
class GuidedProfileDiagnosticReport:
    profile_name: str
    profile_version: str
    frames_evaluated: int
    accepted_frames: int
    visually_valid_frames: int
    rejected_frames: int
    metrics: tuple[MetricDiagnostic, ...]
    rejection_controls: tuple[RejectionControlDiagnostic, ...]
    pose: PoseDiagnostic
    interocular: InterocularDiagnostic
    detected_face_count_histogram: tuple[tuple[int, int], ...]
    rejection_counting_notice: str
    privacy_notice: str


class GuidedProfileDiagnosticCollector:
    """Retain only numeric quality values, poses and aggregate face counts."""

    def __init__(self, policy: GuidedCapturePolicy, profile_name: str,
                 profile_version: str) -> None:
        self.policy = policy
        self.profile_name = profile_name
        self.profile_version = profile_version
        self._frames = self._accepted = self._visual = 0
        self._values: dict[str, dict[str, list[float]]] = {
            name: {cohort: [] for cohort in COHORTS} for name in _metric_names()
        }
        self._reasons: Counter[str] = Counter()
        self._face_counts: Counter[int] = Counter()
        self._pose_pairs: Counter[tuple[str, str]] = Counter()

    def record(self, result: GuidedCaptureResult, detected_face_count: int) -> None:
        """Extract safe scalars immediately; never retain the result or its embedding."""
        self._frames += 1
        self._accepted += int(result.accepted)
        self._visual += int(result.visual_quality_passed)
        self._face_counts[int(detected_face_count)] += 1
        if not result.accepted:
            self._reasons.update(reason.value for reason in result.reasons)
        cohorts = ["rejected" if not result.accepted else "accepted"]
        if result.visual_quality_passed:
            cohorts.append("visually_valid")
        metrics = result.quality_metrics
        values = {
            "confidence": metrics.detection_confidence,
            "relative_face_size": metrics.relative_face_size,
            "interocular_distance": metrics.normalized_interocular_distance,
            "visibility": metrics.visible_box_ratio,
            "centering_offset": _centering(metrics.center_offset_x, metrics.center_offset_y),
            "blur_variance": metrics.blur_variance,
            "mean_illumination": metrics.mean_illumination,
            "contrast": metrics.contrast,
        }
        for name, value in values.items():
            if value is not None and np.isfinite(value):
                for cohort in cohorts:
                    self._values[name][cohort].append(float(value))
        # Pose is meaningful only when aligned landmark geometry was evaluable.
        if metrics.eye_nose_yaw_ratio is not None and metrics.mouth_nose_yaw_ratio is not None:
            self._pose_pairs[(result.requested_pose.value, result.estimated_pose.value)] += 1

    def report(self) -> GuidedProfileDiagnosticReport:
        rejected = self._frames - self._accepted
        metrics = tuple(
            MetricDiagnostic(
                name, _limit(name, self.policy),
                _distribution(self._values[name]["accepted"]),
                _distribution(self._values[name]["visually_valid"]),
                _distribution(self._values[name]["rejected"]),
            ) for name in _metric_names()
        )
        controls = tuple(
            RejectionControlDiagnostic(
                reason, count, count * 100.0 / rejected if rejected else 0.0
            ) for reason, count in sorted(self._reasons.items(), key=lambda item: (-item[1], item[0]))
        )
        all_interocular = [
            *self._values["interocular_distance"]["accepted"],
            *self._values["interocular_distance"]["rejected"],
        ]
        below = sum(value < self.policy.min_interocular_distance for value in all_interocular)
        return GuidedProfileDiagnosticReport(
            self.profile_name, self.profile_version, self._frames, self._accepted,
            self._visual, rejected, metrics, controls, self._pose_report(),
            InterocularDiagnostic(
                self.policy.min_interocular_distance, len(all_interocular), below,
                below * 100.0 / len(all_interocular) if all_interocular else 0.0,
                _distribution(all_interocular),
            ),
            tuple(sorted(self._face_counts.items())),
            "A rejected frame may fail multiple controls; percentages are per rejected frame "
            "and therefore may sum to more than 100%.",
            "Aggregates only: no images, identities, landmarks or embeddings are retained.",
        )

    def _pose_report(self) -> PoseDiagnostic:
        requested: Counter[str] = Counter()
        estimated: Counter[str] = Counter()
        for (left, right), count in self._pose_pairs.items():
            requested[left] += count
            estimated[right] += count
        poses = tuple(pose.value for pose in CapturePose)
        matrix = tuple((left, tuple((right, self._pose_pairs[(left, right)])
                                   for right in poses)) for left in poses)
        total = sum(self._pose_pairs.values())
        unknown = estimated[CapturePose.UNKNOWN.value]
        matches = sum(count for (left, right), count in self._pose_pairs.items() if left == right)
        return PoseDiagnostic(
            total, {
                "frontal_max_yaw_ratio": self.policy.frontal_max_yaw_ratio,
                "slight_turn_min_yaw_ratio": self.policy.slight_turn_min_yaw_ratio,
                "slight_turn_max_yaw_ratio": self.policy.slight_turn_max_yaw_ratio,
                "ambiguity_tolerance": self.policy.pose_ambiguity_tolerance,
            }, tuple(sorted(requested.items())), tuple(sorted(estimated.items())), matrix,
            unknown * 100.0 / total if total else 0.0,
            matches * 100.0 / total if total else 0.0,
        )


def _metric_names() -> tuple[str, ...]:
    return (
        "confidence", "relative_face_size", "interocular_distance", "visibility",
        "centering_offset", "blur_variance", "mean_illumination", "contrast",
    )


def _distribution(values: list[float]) -> NumericDistribution:
    if not values:
        return NumericDistribution(0, None, None, None, None, ())
    array = np.asarray(values, dtype=np.float64)
    return NumericDistribution(
        len(values), float(array.min()), float(array.mean()), float(np.median(array)),
        float(array.max()), tuple((value, float(np.percentile(array, value)))
                                  for value in PERCENTILES),
    )


def _centering(x: float | None, y: float | None) -> float | None:
    if x is None or y is None:
        return None
    return float(np.hypot(x, y))


def _limit(name: str, policy: GuidedCapturePolicy) -> Any:
    return {
        "confidence": {"minimum": policy.min_detection_confidence},
        "relative_face_size": {"minimum": policy.min_relative_face_size},
        "interocular_distance": {"minimum": policy.min_interocular_distance},
        "visibility": {"minimum": policy.min_visible_box_ratio},
        "centering_offset": {
            "maximum_x": policy.max_center_offset_x,
            "maximum_y": policy.max_center_offset_y,
        },
        "blur_variance": {"minimum": policy.min_blur_variance},
        "mean_illumination": {
            "minimum": policy.min_mean_illumination,
            "maximum": policy.max_mean_illumination,
        },
        "contrast": {"minimum": policy.min_contrast},
    }[name]
