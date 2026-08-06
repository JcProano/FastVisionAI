"""Non-decisional diagnostics for overlap in calibration distributions."""

from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import combinations
from typing import Mapping, Sequence

import numpy as np

from src.engine.calibration.contracts import CalibrationSample
from src.engine.calibration.service import CalibrationError


@dataclass(frozen=True, slots=True)
class DiagnosticPolicy:
    near_duplicate_similarity: float = 0.98
    centroid_min_similarity: float = 0.20
    outlier_iqr_multiplier: float = 1.5
    identity_pair_warning_similarity: float = 0.80

    def __post_init__(self) -> None:
        for value in (
            self.near_duplicate_similarity, self.centroid_min_similarity,
            self.identity_pair_warning_similarity,
        ):
            if not math.isfinite(value) or not -1 <= value <= 1:
                raise ValueError("similarity heuristics must be finite and between -1 and 1")
        if not math.isfinite(self.outlier_iqr_multiplier) or self.outlier_iqr_multiplier < 0:
            raise ValueError("outlier_iqr_multiplier must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class SimilaritySummary:
    count: int
    minimum: float | None
    mean: float | None
    median: float | None
    maximum: float | None


@dataclass(frozen=True, slots=True)
class SampleReference:
    temporary_identity_id: str
    session_id: str
    sample_index: int
    alignment_quality: str


@dataclass(frozen=True, slots=True)
class SampleDiagnostic:
    sample: SampleReference
    mean_within_identity_similarity: float | None
    centroid_similarity: float
    near_duplicate_with: tuple[SampleReference, ...]
    outlier: bool
    excessively_different_from_identity_center: bool


@dataclass(frozen=True, slots=True)
class GroupSummary:
    left: str
    right: str
    similarity: SimilaritySummary


@dataclass(frozen=True, slots=True)
class MatrixCell:
    left_identity: str
    left_session: str
    right_identity: str
    right_session: str
    similarity: SimilaritySummary


@dataclass(frozen=True, slots=True)
class CalibrationDiagnosticReport:
    genuine_by_identity: tuple[GroupSummary, ...]
    impostor_by_identity_pair: tuple[GroupSummary, ...]
    within_session: SimilaritySummary
    between_sessions_same_identity: SimilaritySummary
    between_identities: SimilaritySummary
    by_session: tuple[GroupSummary, ...]
    similarity_matrix: tuple[MatrixCell, ...]
    samples: tuple[SampleDiagnostic, ...]
    warnings: tuple[str, ...]
    heuristic_notice: str


class CalibrationDiagnosticService:
    """Explain distribution overlap without producing matches or thresholds."""

    def __init__(self, policy: DiagnosticPolicy | None = None) -> None:
        self.policy = policy or DiagnosticPolicy()

    def analyze(
        self, groups: Mapping[str, Sequence[CalibrationSample]]
    ) -> CalibrationDiagnosticReport:
        ordered = _validate(groups)
        genuine: list[GroupSummary] = []
        impostor: list[GroupSummary] = []
        session_nodes: dict[tuple[str, str], list[tuple[int, CalibrationSample]]] = {}
        within_session_scores: list[float] = []
        same_identity_cross_session: list[float] = []
        different_identity_scores: list[float] = []
        sample_rows: list[SampleDiagnostic] = []
        warnings: list[str] = []

        for identity, samples in ordered:
            genuine.append(GroupSummary(identity, identity, _summary(_within_scores(samples))))
            sessions: dict[str, list[tuple[int, CalibrationSample]]] = {}
            for index, sample in enumerate(samples):
                sessions.setdefault(sample.metadata.session_id, []).append((index, sample))
            if len(sessions) == 1:
                warnings.append(f"identity '{identity}' has only one session")
            session_nodes.update({(identity, key): value for key, value in sessions.items()})
            for values in sessions.values():
                within_session_scores.extend(_within_scores([item[1] for item in values]))
            for left, right in combinations(sessions.values(), 2):
                same_identity_cross_session.extend(_cross_scores(
                    [item[1] for item in left], [item[1] for item in right]
                ))
            sample_rows.extend(self._sample_diagnostics(identity, samples))

        for (left_id, left), (right_id, right) in combinations(ordered, 2):
            scores = _cross_scores(left, right)
            impostor.append(GroupSummary(left_id, right_id, _summary(scores)))
            different_identity_scores.extend(scores)
            if scores and float(np.mean(scores)) >= self.policy.identity_pair_warning_similarity:
                warnings.append(
                    f"temporary identities '{left_id}' and '{right_id}' have unusually high "
                    "mean similarity; this is diagnostic only and is not an identity conclusion"
                )

        by_session = tuple(
            GroupSummary(f"{identity}/{session}", f"{identity}/{session}",
                         _summary(_within_scores([item[1] for item in values])))
            for (identity, session), values in sorted(session_nodes.items())
        )
        matrix: list[MatrixCell] = []
        nodes = sorted(session_nodes)
        for left_index, left_key in enumerate(nodes):
            for right_key in nodes[left_index:]:
                left = [item[1] for item in session_nodes[left_key]]
                right = [item[1] for item in session_nodes[right_key]]
                scores = _within_scores(left) if left_key == right_key else _cross_scores(left, right)
                matrix.append(MatrixCell(*left_key, *right_key, _summary(scores)))

        return CalibrationDiagnosticReport(
            tuple(genuine), tuple(impostor), _summary(within_session_scores),
            _summary(same_identity_cross_session), _summary(different_identity_scores),
            by_session, tuple(matrix), tuple(sample_rows), tuple(warnings),
            "All flags use configurable diagnostic heuristics; none is recognition or identity evidence.",
        )

    def _sample_diagnostics(self, identity, samples):
        vectors = np.stack([_vector(item) for item in samples])
        center = vectors.mean(axis=0)
        center_norm = float(np.linalg.norm(center))
        center = center / center_norm if center_norm > 1e-12 else center
        means: list[float | None] = []
        for index, sample in enumerate(samples):
            scores = [_cosine(sample, other) for other_index, other in enumerate(samples)
                      if other_index != index]
            means.append(float(np.mean(scores)) if scores else None)
        finite_means = np.asarray([value for value in means if value is not None])
        lower_fence = float("-inf")
        if finite_means.size >= 4:
            q1, q3 = np.percentile(finite_means, [25, 75])
            lower_fence = float(q1 - self.policy.outlier_iqr_multiplier * (q3 - q1))
        output = []
        for index, sample in enumerate(samples):
            reference = _reference(identity, index, sample)
            duplicate_refs = tuple(
                _reference(identity, other_index, other)
                for other_index, other in enumerate(samples)
                if other_index != index and _cosine(sample, other) >= self.policy.near_duplicate_similarity
            )
            centroid_similarity = float(np.clip(np.dot(_vector(sample), center), -1, 1))
            output.append(SampleDiagnostic(
                reference, means[index], centroid_similarity, duplicate_refs,
                means[index] is not None and means[index] < lower_fence,
                centroid_similarity < self.policy.centroid_min_similarity,
            ))
        return output


def _validate(groups):
    if not groups:
        raise CalibrationError("diagnostic dataset is empty")
    expected = None
    ordered = []
    for identity in sorted(groups):
        samples = tuple(groups[identity])
        if not samples:
            raise CalibrationError("diagnostic identity has no samples")
        for sample in samples:
            vector = _vector(sample)
            current = (vector.size, sample.metadata.model, sample.metadata.version,
                       sample.metadata.weights_sha256)
            if sample.metadata.temporary_identity_id != identity:
                raise CalibrationError("diagnostic sample identity mismatch")
            if expected is None:
                expected = current
            elif current != expected:
                raise CalibrationError("incompatible diagnostic model provenance")
        ordered.append((identity, samples))
    return ordered


def _vector(sample):
    vector = np.asarray(sample.embedding)
    if vector.dtype != np.float32 or vector.ndim != 1 or not np.isfinite(vector).all():
        raise CalibrationError("invalid diagnostic embedding")
    if not math.isclose(float(np.linalg.norm(vector)), 1.0, abs_tol=1e-5):
        raise CalibrationError("diagnostic embedding must be L2-normalized")
    return vector


def _cosine(left, right):
    return float(np.clip(np.dot(_vector(left), _vector(right)), -1.0, 1.0))


def _within_scores(samples):
    return [_cosine(left, right) for left, right in combinations(samples, 2)]


def _cross_scores(left, right):
    return [_cosine(a, b) for a in left for b in right]


def _summary(scores):
    if not scores:
        return SimilaritySummary(0, None, None, None, None)
    values = np.asarray(scores, dtype=np.float64)
    return SimilaritySummary(len(scores), float(values.min()), float(values.mean()),
                             float(np.median(values)), float(values.max()))


def _reference(identity, index, sample):
    return SampleReference(identity, sample.metadata.session_id, index,
                           sample.metadata.alignment_quality.value)

