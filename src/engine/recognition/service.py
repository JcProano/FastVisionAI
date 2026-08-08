"""Interpret FaceMatcher scores without introducing implicit biometric policy."""

from __future__ import annotations

from src.engine.alignment import AlignmentQuality
from src.engine.embedding.contracts import FaceEmbedding
from src.engine.face_quality.contracts import FaceQualityScore
from src.engine.gallery import FaceGallery, FaceMatcher, MatchCandidate, MatchDecision

from .contracts import (
    RecognitionCandidate, RecognitionPolicy, RecognitionQuality, RecognitionResult,
    RecognitionState,
)


class RecognitionService:
    def __init__(
        self, gallery: FaceGallery, matcher: FaceMatcher,
        policy: RecognitionPolicy | None = None,
    ) -> None:
        self.gallery = gallery
        self.matcher = matcher
        self.policy = policy or RecognitionPolicy()
        if matcher.policy.automatic_decision_enabled or matcher.policy.threshold is not None:
            raise ValueError("RecognitionService requires a non-deciding FaceMatcher")
        if matcher.top_k < self.policy.top_k:
            raise ValueError("FaceMatcher top_k is smaller than RecognitionPolicy top_k")

    def recognize(
        self, query: FaceEmbedding, quality_score: FaceQualityScore | None = None,
    ) -> RecognitionResult:
        quality = RecognitionQuality(
            None if quality_score is None else quality_score.total_score,
            None if quality_score is None else quality_score.quality_band.value,
            query.alignment_quality.value,
        )
        templates = self.gallery.templates()
        if not templates:
            return self._result(RecognitionState.NO_GALLERY, query, quality)
        if not any(_compatible(query, item.template) for item in templates):
            return self._result(RecognitionState.INCOMPATIBLE, query, quality)

        matched = self.matcher.match(query, self.gallery)
        if matched.decision is not MatchDecision.NOT_EVALUATED:
            raise RuntimeError("FaceMatcher performed an unexpected automatic decision")
        raw = matched.candidates[: self.policy.top_k]
        candidates = tuple(_safe_candidate(item) for item in raw)
        best_match = raw[0] if raw else None
        best = candidates[0] if candidates else None
        second_match = _second_identity_candidate(raw, best_match)
        second = None if second_match is None else second_match.similarity
        margin = None if best is None or second is None else best.similarity - second

        if not self.policy.automatic_decision_enabled:
            state, evaluated = RecognitionState.NOT_EVALUATED, False
        elif not _quality_allows_decision(query, quality_score, self.policy):
            state, evaluated = RecognitionState.NOT_EVALUATED, False
        else:
            threshold = self.policy.match_threshold
            if threshold is None:  # guarded by RecognitionPolicy; defensive for future changes
                raise RuntimeError("automatic recognition policy has no threshold")
            if best is None or best.similarity < threshold:
                state, evaluated = RecognitionState.UNKNOWN, True
            elif (
                self.policy.ambiguity_margin is not None
                and margin is not None
                and margin < self.policy.ambiguity_margin
            ):
                state, evaluated = RecognitionState.AMBIGUOUS, True
            else:
                state, evaluated = RecognitionState.MATCH, True
        return self._result(
            state, query, quality, best, second, margin, candidates, evaluated,
        )

    def _result(
        self, state: RecognitionState, query: FaceEmbedding, quality: RecognitionQuality,
        best: RecognitionCandidate | None = None,
        second: float | None = None,
        margin: float | None = None,
        candidates: tuple[RecognitionCandidate, ...] = (),
        evaluated: bool = False,
    ) -> RecognitionResult:
        return RecognitionResult(
            state, best, None if best is None else best.display_name,
            None if best is None else best.person_id,
            None if best is None else best.similarity, second, margin, quality,
            query.run_id, evaluated, self.policy.policy_name,
            self.policy.policy_version, candidates,
        )


def _compatible(query: FaceEmbedding, template: object) -> bool:
    return bool(
        query.dimension == getattr(template, "dimension")
        and query.model == getattr(template, "model")
        and query.version == getattr(template, "model_version")
        and query.weights_sha256 == getattr(template, "weights_sha256")
    )


def _safe_candidate(candidate: MatchCandidate) -> RecognitionCandidate:
    return RecognitionCandidate(
        candidate.identity.person_id, candidate.identity.display_name,
        candidate.similarity, candidate.rank,
    )


def _second_identity_candidate(
    candidates: tuple[MatchCandidate, ...], best: MatchCandidate | None,
) -> MatchCandidate | None:
    if best is None:
        return None
    return next(
        (item for item in candidates if item.identity.person_id != best.identity.person_id), None
    )


def _quality_allows_decision(
    query: FaceEmbedding, score: FaceQualityScore | None, policy: RecognitionPolicy,
) -> bool:
    if query.alignment_quality is AlignmentQuality.REJECTED:
        return False
    if query.alignment_quality is AlignmentQuality.LOW_QUALITY and not policy.allow_low_quality:
        return False
    if policy.minimum_quality_score is not None:
        return score is not None and score.total_score >= policy.minimum_quality_score
    return True
