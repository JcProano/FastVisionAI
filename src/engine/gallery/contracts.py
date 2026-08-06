"""Typed gallery, template and similarity result contracts."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

import numpy as np

from src.engine.alignment.contracts import AlignmentQuality


@dataclass(frozen=True, slots=True)
class FaceIdentity:
    person_id: str
    display_name: str
    metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if not self.person_id.strip() or not self.display_name.strip():
            raise ValueError("person_id and display_name must be non-empty")
        if self.metadata is not None:
            object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class FaceTemplate:
    identity: FaceIdentity
    embedding: np.ndarray
    dimension: int
    model: str
    model_version: str
    weights_sha256: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    quality: AlignmentQuality = AlignmentQuality.VALID
    source_reference: str | None = None

    def __post_init__(self) -> None:
        vector = np.array(self.embedding, dtype=np.float32, order="C", copy=True)
        if vector.ndim != 1 or self.dimension <= 0 or vector.size != self.dimension:
            raise ValueError("template embedding dimension is invalid")
        if not np.isfinite(vector).all():
            raise ValueError("template embedding contains non-finite values")
        norm = float(np.linalg.norm(vector))
        if not math.isclose(norm, 1.0, abs_tol=1e-5):
            raise ValueError("template embedding must be L2-normalized")
        if not self.model.strip() or not self.model_version.strip() or not self.weights_sha256.strip():
            raise ValueError("template model provenance is required")
        if self.created_at.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        if self.quality is AlignmentQuality.REJECTED:
            raise ValueError("rejected faces cannot become templates")
        vector.setflags(write=False)
        object.__setattr__(self, "embedding", vector)


@dataclass(frozen=True, slots=True)
class ModelCompatibility:
    compatible: bool
    dimension: bool
    model: bool
    model_version: bool
    weights_sha256: bool
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class MatchCandidate:
    identity: FaceIdentity
    similarity: float
    template_index: int
    quality: AlignmentQuality
    model_compatibility: ModelCompatibility
    rank: int


@dataclass(frozen=True, slots=True)
class MatchQuery:
    run_id: str
    face_index: int
    dimension: int
    model: str
    model_version: str
    weights_sha256: str
    alignment_quality: AlignmentQuality


class MatchDecision(str, Enum):
    NOT_EVALUATED = "not_evaluated"
    MATCH = "match"
    NO_MATCH = "no_match"


@dataclass(frozen=True, slots=True)
class MatchPolicy:
    automatic_decision_enabled: bool = False
    threshold: float | None = None

    def __post_init__(self) -> None:
        if self.threshold is not None and (
            not math.isfinite(self.threshold) or not -1.0 <= self.threshold <= 1.0
        ):
            raise ValueError("threshold must be finite and between -1 and 1")
        if self.automatic_decision_enabled and self.threshold is None:
            raise ValueError("automatic decisions require an explicit threshold")


@dataclass(frozen=True, slots=True)
class MatchResult:
    query: MatchQuery
    candidates: tuple[MatchCandidate, ...]
    best_candidate: MatchCandidate | None
    decision: MatchDecision
    policy: MatchPolicy
