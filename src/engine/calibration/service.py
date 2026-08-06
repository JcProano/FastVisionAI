"""Pure, deterministic face-similarity calibration analysis."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import combinations
from typing import Mapping, Sequence

import numpy as np

from src.engine.alignment.contracts import AlignmentQuality
from src.engine.calibration.contracts import (
    CalibrationPolicy, CalibrationQualitySummary, CalibrationReport, CalibrationSample,
    CalibrationWarning, DistributionStatistics, EstimatedEER, ThresholdRates,
)


class CalibrationError(ValueError):
    """A safe validation error that never contains biometric vectors."""


@dataclass(frozen=True, slots=True)
class _Pair:
    similarity: float
    includes_low_quality: bool


class CalibrationService:
    def __init__(self, policy: CalibrationPolicy | None = None) -> None:
        self.policy = policy or CalibrationPolicy()

    def calibrate(
        self,
        embedding_groups: Mapping[str, Sequence[CalibrationSample]],
        thresholds: Sequence[float],
        run_id: str,
        *,
        synthetic_validation: bool = False,
    ) -> CalibrationReport:
        if not run_id.strip():
            raise CalibrationError("run_id must be non-empty")
        ordered_groups = self._validate_groups(embedding_groups)
        checked_thresholds = _validate_thresholds(thresholds)
        first = ordered_groups[0][1][0]
        model = first.metadata.model
        version = first.metadata.version
        sha = first.metadata.weights_sha256
        dimension = _vector(first).size

        genuine: list[_Pair] = []
        possible_impostors: list[_Pair] = []
        for _, samples in ordered_groups:
            genuine.extend(_make_pairs(samples))
        for (_, left), (_, right) in combinations(ordered_groups, 2):
            possible_impostors.extend(_cross_pairs(left, right))

        impostors = possible_impostors
        sampled = False
        limit = self.policy.max_impostor_pairs
        if limit is not None and len(impostors) > limit:
            indices = sorted(random.Random(self.policy.impostor_sampling_seed).sample(
                range(len(impostors)), limit
            ))
            impostors = [impostors[index] for index in indices]
            sampled = True

        genuine_scores = [item.similarity for item in genuine]
        impostor_scores = [item.similarity for item in impostors]
        rates = tuple(_rates(value, genuine_scores, impostor_scores) for value in checked_thresholds)
        valid = sum(
            sample.metadata.alignment_quality is AlignmentQuality.VALID
            for _, samples in ordered_groups for sample in samples
        )
        low = sum(len(samples) for _, samples in ordered_groups) - valid
        warnings = self._warnings(ordered_groups, len(genuine), len(impostors), valid, low)
        return CalibrationReport(
            model=model, version=version, weights_sha256=sha, embedding_dimension=dimension,
            identity_count=len(ordered_groups),
            templates_per_identity=tuple((key, len(samples)) for key, samples in ordered_groups),
            quality=CalibrationQualitySummary(
                valid, low,
                sum(item.includes_low_quality for item in genuine),
                sum(item.includes_low_quality for item in impostors),
            ),
            genuine_distribution=_statistics(genuine_scores, self.policy),
            impostor_distribution=_statistics(impostor_scores, self.policy),
            total_possible_impostor_pairs=len(possible_impostors),
            used_impostor_pairs=len(impostors), impostor_pairs_sampled=sampled,
            threshold_rates=rates,
            estimated_eer=_estimated_eer(genuine_scores, impostor_scores),
            warnings=warnings, generated_at=datetime.now(timezone.utc), run_id=run_id,
            synthetic_validation=synthetic_validation,
        )

    def _validate_groups(
        self, groups: Mapping[str, Sequence[CalibrationSample]]
    ) -> list[tuple[str, tuple[CalibrationSample, ...]]]:
        if len(groups) < self.policy.min_identities:
            raise CalibrationError("insufficient temporary identities")
        ordered = [(key, tuple(groups[key])) for key in sorted(groups)]
        provenance: tuple[int, str, str, str] | None = None
        for identity, samples in ordered:
            if not identity or len(samples) < self.policy.min_samples_per_identity:
                raise CalibrationError("insufficient samples for a temporary identity")
            for sample in samples:
                if sample.metadata.temporary_identity_id != identity:
                    raise CalibrationError("sample temporary identity does not match its group")
                vector = _vector(sample)
                current = (vector.size, sample.metadata.model, sample.metadata.version,
                           sample.metadata.weights_sha256)
                if provenance is None:
                    provenance = current
                elif current != provenance:
                    raise CalibrationError("incompatible biometric model provenance")
        return ordered

    def _warnings(self, groups, genuine_count, impostor_count, valid, low):
        samples = [sample for _, values in groups for sample in values]
        output: list[CalibrationWarning] = []
        if len({item.metadata.session_id for item in samples}) == 1:
            output.append(CalibrationWarning.SINGLE_SESSION)
        if len(groups) < self.policy.warning_min_identities:
            output.append(CalibrationWarning.FEW_IDENTITIES)
        if genuine_count < self.policy.warning_min_genuine_pairs:
            output.append(CalibrationWarning.FEW_GENUINE_PAIRS)
        if impostor_count < self.policy.warning_min_impostor_pairs:
            output.append(CalibrationWarning.FEW_IMPOSTOR_PAIRS)
        if low > valid:
            output.append(CalibrationWarning.LOW_QUALITY_PREDOMINATES)
        conditions = {
            (item.metadata.source_identifier, item.metadata.resolution)
            for item in samples
        }
        if len(conditions) == 1:
            output.append(CalibrationWarning.HOMOGENEOUS_CAPTURE_CONDITIONS)
        return tuple(output)


def _vector(sample: CalibrationSample) -> np.ndarray:
    value = np.asarray(sample.embedding)
    if value.dtype != np.float32 or value.ndim != 1 or value.size == 0:
        raise CalibrationError("sample embedding must be one-dimensional float32")
    if not np.isfinite(value).all():
        raise CalibrationError("sample embedding contains invalid numeric values")
    norm = float(np.linalg.norm(value))
    if not math.isclose(norm, 1.0, abs_tol=1e-5):
        raise CalibrationError("sample embedding must be L2-normalized")
    return value


def _similarity(left: CalibrationSample, right: CalibrationSample) -> float:
    return float(np.clip(np.dot(_vector(left), _vector(right)), -1.0, 1.0))


def _make_pairs(samples):
    return [_Pair(_similarity(left, right), _low(left, right))
            for left, right in combinations(samples, 2)]


def _cross_pairs(left, right):
    return [_Pair(_similarity(a, b), _low(a, b)) for a in left for b in right]


def _low(left, right):
    return (left.metadata.alignment_quality is AlignmentQuality.LOW_QUALITY or
            right.metadata.alignment_quality is AlignmentQuality.LOW_QUALITY)


def _validate_thresholds(values):
    result = sorted(set(float(value) for value in values))
    if not result or any(not math.isfinite(value) or not -1 <= value <= 1 for value in result):
        raise CalibrationError("thresholds must be finite values between -1 and 1")
    return tuple(result)


def _rates(threshold, genuine, impostors):
    # The boundary is intentional: similarity == threshold is accepted.
    false_accepts = sum(score >= threshold for score in impostors)
    false_rejects = sum(score < threshold for score in genuine)
    return ThresholdRates(
        threshold, false_accepts, len(impostors), false_accepts / len(impostors),
        false_rejects, len(genuine), false_rejects / len(genuine),
    )


def _statistics(scores, policy):
    if not scores:
        raise CalibrationError("calibration distribution has no pairs")
    values = np.asarray(scores, dtype=np.float64)
    counts, edges = np.histogram(values, bins=policy.histogram_bins, range=(-1.0, 1.0))
    return DistributionStatistics(
        len(scores), float(values.min()), float(values.mean()), float(np.median(values)),
        float(values.max()), float(values.std()),
        tuple((p, float(np.percentile(values, p))) for p in policy.percentiles),
        tuple(float(item) for item in edges), tuple(int(item) for item in counts),
    )


def _estimated_eer(genuine, impostors):
    candidates = sorted(set([-1.0, 1.0, *genuine, *impostors]))
    candidates += [(a + b) / 2 for a, b in zip(candidates, candidates[1:])]
    values = [_rates(value, genuine, impostors) for value in sorted(set(candidates))]
    best = min(values, key=lambda item: (abs(item.far - item.frr), item.threshold))
    return EstimatedEER(True, best.threshold, best.far, best.frr,
                        (best.far + best.frr) / 2, abs(best.far - best.frr),
                        "minimum absolute FAR-FRR gap over observed scores and midpoints")
