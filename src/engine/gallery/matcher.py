"""Cosine score calculation with policy decisions kept separate."""

from __future__ import annotations

import numpy as np

from src.engine.embedding.contracts import FaceEmbedding
from src.engine.gallery.contracts import (
    MatchCandidate, MatchDecision, MatchPolicy, MatchQuery, MatchResult,
    ModelCompatibility,
)
from src.engine.gallery.gallery import FaceGallery, GalleryCompatibilityError


class FaceMatcher:
    def __init__(self, top_k: int = 5, policy: MatchPolicy | None = None) -> None:
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        self.top_k = top_k
        self.policy = policy or MatchPolicy()

    def match(self, query: FaceEmbedding, gallery: FaceGallery) -> MatchResult:
        query_metadata = MatchQuery(
            query.run_id, query.face_index, query.dimension, query.model,
            query.version, query.weights_sha256, query.alignment_quality,
        )
        scored: list[tuple[float, int, object, ModelCompatibility]] = []
        for indexed in gallery.templates():
            template = indexed.template
            compatibility = _compatibility(query, template)
            if not compatibility.compatible:
                raise GalleryCompatibilityError("query biometric provenance is incompatible")
            similarity = float(np.dot(query.embedding, template.embedding))
            similarity = max(-1.0, min(1.0, similarity))
            scored.append((similarity, indexed.index, template, compatibility))
        scored.sort(key=lambda item: (-item[0], item[1], item[2].identity.person_id))
        candidates = tuple(
            MatchCandidate(
                identity=item[2].identity,
                similarity=item[0],
                template_index=item[1],
                quality=item[2].quality,
                model_compatibility=item[3],
                rank=rank,
            )
            for rank, item in enumerate(scored[: self.top_k], start=1)
        )
        best = candidates[0] if candidates else None
        decision = MatchDecision.NOT_EVALUATED
        if self.policy.automatic_decision_enabled:
            decision = (
                MatchDecision.MATCH
                if best is not None and best.similarity >= self.policy.threshold
                else MatchDecision.NO_MATCH
            )
        return MatchResult(query_metadata, candidates, best, decision, self.policy)


def _compatibility(query: FaceEmbedding, template) -> ModelCompatibility:
    checks = (
        query.dimension == template.dimension,
        query.model == template.model,
        query.version == template.model_version,
        query.weights_sha256 == template.weights_sha256,
    )
    labels = ("dimension", "model", "model_version", "weights_sha256")
    reasons = tuple(label for label, valid in zip(labels, checks) if not valid)
    return ModelCompatibility(all(checks), *checks, reasons)
