"""Safe contracts for structured face-recognition interpretation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum


class RecognitionState(str, Enum):
    NOT_EVALUATED = "not_evaluated"
    MATCH = "match"
    UNKNOWN = "unknown"
    AMBIGUOUS = "ambiguous"
    INCOMPATIBLE = "incompatible"
    NO_GALLERY = "no_gallery"


@dataclass(frozen=True, slots=True)
class RecognitionPolicy:
    automatic_decision_enabled: bool = False
    match_threshold: float | None = None
    ambiguity_margin: float | None = None
    top_k: int = 5
    minimum_quality_score: float | None = None
    allow_low_quality: bool = False
    policy_name: str = "recognition_disabled"
    policy_version: str = "1.0"

    def __post_init__(self) -> None:
        if self.top_k <= 0:
            raise ValueError("top_k must be positive")
        if self.match_threshold is not None and not _bounded(
            self.match_threshold, -1.0, 1.0
        ):
            raise ValueError("match_threshold must be finite and within -1..1")
        if self.ambiguity_margin is not None and not _bounded(
            self.ambiguity_margin, 0.0, 2.0
        ):
            raise ValueError("ambiguity_margin must be finite and within 0..2")
        if self.minimum_quality_score is not None and not _bounded(
            self.minimum_quality_score, 0.0, 100.0
        ):
            raise ValueError("minimum_quality_score must be finite and within 0..100")
        if self.automatic_decision_enabled and self.match_threshold is None:
            raise ValueError("automatic recognition requires an explicit match_threshold")
        if not self.policy_name.strip() or not self.policy_version.strip():
            raise ValueError("policy_name and policy_version must be non-empty")


@dataclass(frozen=True, slots=True)
class RecognitionQuality:
    score: float | None
    band: str | None
    alignment_quality: str

    def __post_init__(self) -> None:
        if self.score is not None and not _bounded(self.score, 0.0, 100.0):
            raise ValueError("quality score must be finite and within 0..100")
        if not self.alignment_quality.strip():
            raise ValueError("alignment_quality must be non-empty")


@dataclass(frozen=True, slots=True)
class RecognitionCandidate:
    person_id: str
    display_name: str
    similarity: float
    rank: int

    def __post_init__(self) -> None:
        if not self.person_id.strip() or not self.display_name.strip():
            raise ValueError("candidate identity fields must be non-empty")
        if not _bounded(self.similarity, -1.0, 1.0):
            raise ValueError("candidate similarity must be finite and within -1..1")
        if self.rank <= 0:
            raise ValueError("candidate rank must be positive")


@dataclass(frozen=True, slots=True)
class RecognitionResult:
    state: RecognitionState
    primary_candidate: RecognitionCandidate | None
    display_name: str | None
    person_id: str | None
    similarity: float | None
    second_best_similarity: float | None
    margin: float | None
    quality: RecognitionQuality
    run_id: str
    evaluated: bool
    policy_name: str
    policy_version: str
    candidates: tuple[RecognitionCandidate, ...] = ()

    def __post_init__(self) -> None:
        for value in (self.similarity, self.second_best_similarity):
            if value is not None and not _bounded(value, -1.0, 1.0):
                raise ValueError("recognition similarity must be finite and within -1..1")
        if self.margin is not None and not _bounded(self.margin, 0.0, 2.0):
            raise ValueError("recognition margin must be finite and within 0..2")
        if not self.run_id.strip() or not self.policy_name.strip() or not self.policy_version.strip():
            raise ValueError("run_id and policy provenance must be non-empty")
        if self.primary_candidate is None and any(
            value is not None for value in (self.display_name, self.person_id, self.similarity)
        ):
            raise ValueError("candidate summary requires a primary_candidate")
        if self.state in {RecognitionState.MATCH, RecognitionState.UNKNOWN,
                          RecognitionState.AMBIGUOUS} and not self.evaluated:
            raise ValueError("decision states require evaluated=true")
        if self.state in {RecognitionState.NOT_EVALUATED, RecognitionState.INCOMPATIBLE,
                          RecognitionState.NO_GALLERY} and self.evaluated:
            raise ValueError("non-decision states require evaluated=false")


def _bounded(value: float, minimum: float, maximum: float) -> bool:
    return math.isfinite(value) and minimum <= value <= maximum
