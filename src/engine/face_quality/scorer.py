"""Deterministic continuous quality scoring; never an acceptance decision.

Higher-is-better metrics use clamp((value-minimum)/(full_score-minimum), 0, 1).
Centering uses 1-clamp((offset-ideal)/(maximum-ideal), 0, 1), where offset is
Euclidean. Illumination is 1 inside its ideal interval and falls linearly to 0
at either absolute limit. Pose values are explicit profile constants. Component
values are multiplied by weights, summed, multiplied by configured penalties,
then clamped to 0..100. Structural failures always yield INVALID and zero.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Sequence

from src.engine.alignment.contracts import AlignmentStatus
from src.engine.capture_quality.contracts import (
    CapturePose, GuidedCaptureState, GuidedQualityMetrics,
)
from src.engine.face_quality.contracts import (
    CenteringLimit, FaceQualityScore, FaceQualityScoringProfile, FaceQualityWeights,
    HigherIsBetterLimit, IlluminationLimit, PoseScores, QualityBand,
    QualityBandThresholds,
)


class FaceQualityScorer:
    """Compute an informative score without changing guided-capture policy results."""

    def __init__(self, profile: FaceQualityScoringProfile) -> None:
        self.profile = profile

    def score(
        self,
        metrics: GuidedQualityMetrics,
        requested_pose: CapturePose,
        estimated_pose: CapturePose,
        reasons: Sequence[GuidedCaptureState],
        alignment_status: AlignmentStatus | None,
        detection_confidence: float | None,
        run_id: str,
        face_index: int | None,
    ) -> FaceQualityScore:
        reason_names = tuple(reason.value for reason in reasons)
        structural = (
            alignment_status is not AlignmentStatus.ALIGNED or
            any(reason in self.profile.structural_invalid_states for reason in reason_names)
        )
        if structural:
            return FaceQualityScore(
                0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                QualityBand.INVALID, self.profile.profile_name, self.profile.profile_version,
                ("Structural face input is invalid; component scoring was not applied.",),
                run_id, face_index,
            )

        confidence = detection_confidence
        if confidence is None:
            confidence = metrics.detection_confidence
        components = {
            "detection": _higher(confidence, self.profile.detection),
            "size": _higher(metrics.relative_face_size, self.profile.size),
            "interocular": _higher(metrics.normalized_interocular_distance,
                                   self.profile.interocular),
            "visibility": _higher(metrics.visible_box_ratio, self.profile.visibility),
            "centering": _centering(metrics.center_offset_x, metrics.center_offset_y,
                                    self.profile.centering),
            "sharpness": _higher(metrics.blur_variance, self.profile.sharpness),
            "illumination": _illumination(metrics.mean_illumination,
                                          self.profile.illumination),
            "contrast": _higher(metrics.contrast, self.profile.contrast),
            "pose": _pose(requested_pose, estimated_pose, self.profile.pose),
        }
        weights = self.profile.weights
        weighted = math.fsum((
            components["detection"] * weights.detection,
            components["size"] * weights.size,
            components["interocular"] * weights.interocular,
            components["visibility"] * weights.visibility,
            components["centering"] * weights.centering,
            components["sharpness"] * weights.sharpness,
            components["illumination"] * weights.illumination,
            components["contrast"] * weights.contrast,
            components["pose"] * weights.pose,
        ))
        penalty = 1.0
        explanations: list[str] = []
        for reason in dict.fromkeys(reason_names):
            multiplier = self.profile.critical_penalties.get(reason)
            if multiplier is not None:
                penalty *= multiplier
                explanations.append(f"Configured penalty applied for quality state: {reason}.")
        for name, value in components.items():
            if value < 0.5:
                explanations.append(f"Low normalized quality component: {name}.")
        total = _clamp(weighted * penalty) * 100.0
        component_scores = {name: _clamp(value) * 100.0 for name, value in components.items()}
        return FaceQualityScore(
            total, component_scores["detection"], component_scores["size"],
            component_scores["interocular"], component_scores["visibility"],
            component_scores["centering"], component_scores["sharpness"],
            component_scores["illumination"], component_scores["contrast"],
            component_scores["pose"], _band(total, self.profile.bands),
            self.profile.profile_name, self.profile.profile_version, tuple(explanations),
            run_id, face_index,
        )


def load_face_quality_profile(path: Path) -> FaceQualityScoringProfile:
    try:
        root = json.loads(path.read_text(encoding="utf-8"))
        limits = root["normalization_limits"]
        return FaceQualityScoringProfile(
            profile_name=str(root["profile_name"]),
            profile_version=str(root["profile_version"]),
            weights=FaceQualityWeights(**root["weights"]),
            detection=HigherIsBetterLimit(**limits["detection"]),
            size=HigherIsBetterLimit(**limits["size"]),
            interocular=HigherIsBetterLimit(**limits["interocular"]),
            visibility=HigherIsBetterLimit(**limits["visibility"]),
            centering=CenteringLimit(**limits["centering"]),
            sharpness=HigherIsBetterLimit(**limits["sharpness"]),
            illumination=IlluminationLimit(**limits["illumination"]),
            contrast=HigherIsBetterLimit(**limits["contrast"]),
            pose=PoseScores(**limits["pose"]),
            bands=QualityBandThresholds(**root["bands"]),
            critical_penalties=root["critical_penalties"],
            structural_invalid_states=tuple(root["structural_invalid_states"]),
        )
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("invalid face quality scoring profile") from exc


def _higher(value: float | None, limits: HigherIsBetterLimit) -> float:
    if value is None or not math.isfinite(value):
        return 0.0
    return _clamp((value - limits.minimum) / (limits.full_score - limits.minimum))


def _centering(x: float | None, y: float | None, limits: CenteringLimit) -> float:
    if x is None or y is None or not math.isfinite(x) or not math.isfinite(y):
        return 0.0
    offset = math.hypot(x, y)
    return 1.0 - _clamp(
        (offset - limits.ideal_offset) / (limits.maximum_offset - limits.ideal_offset)
    )


def _illumination(value: float | None, limits: IlluminationLimit) -> float:
    if value is None or not math.isfinite(value):
        return 0.0
    if limits.ideal_minimum <= value <= limits.ideal_maximum:
        return 1.0
    if value < limits.ideal_minimum:
        return _clamp((value - limits.absolute_minimum) /
                      (limits.ideal_minimum - limits.absolute_minimum))
    return _clamp((limits.absolute_maximum - value) /
                  (limits.absolute_maximum - limits.ideal_maximum))


def _pose(requested: CapturePose, estimated: CapturePose, scores: PoseScores) -> float:
    if estimated is CapturePose.UNKNOWN:
        return scores.unknown
    return scores.requested_match if estimated is requested else scores.requested_mismatch


def _band(score: float, thresholds: QualityBandThresholds) -> QualityBand:
    if score >= thresholds.excellent:
        return QualityBand.EXCELLENT
    if score >= thresholds.good:
        return QualityBand.GOOD
    if score >= thresholds.acceptable:
        return QualityBand.ACCEPTABLE
    return QualityBand.POOR


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))

