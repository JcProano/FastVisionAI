"""Use case for interpreting biometric similarity under an explicit policy."""

from __future__ import annotations

from ..domain.ports import (
    BiometricEmbeddingPort,
    BiometricGalleryPort,
    FaceMatcherPort,
    FaceQualityScorePort,
    MatchCandidatePort,
)
from ..domain.recognition import (
    RecognitionCandidate,
    RecognitionPolicy,
    RecognitionQuality,
    RecognitionResult,
    RecognitionState,
)


class RecognizeFaceUseCase:
    def __init__(
        self,
        gallery: BiometricGalleryPort,
        matcher: FaceMatcherPort,
        policy: RecognitionPolicy | None = None,
    ) -> None:
        self.gallery = gallery
        self.matcher = matcher
        self.policy = policy or RecognitionPolicy()
        if (
            matcher.policy.automatic_decision_enabled
            or matcher.policy.threshold is not None
        ):
            raise ValueError("recognition requires a non-deciding matcher")
        if matcher.top_k < self.policy.top_k:
            raise ValueError("matcher top_k is smaller than recognition top_k")

    def execute(
        self,
        query: BiometricEmbeddingPort,
        quality_score: FaceQualityScorePort | None = None,
    ) -> RecognitionResult:
        quality = RecognitionQuality(
            None if quality_score is None else quality_score.total_score,
            None
            if quality_score is None
            else _enum_value(quality_score.quality_band),
            _enum_value(query.alignment_quality),
        )
        templates = self.gallery.templates()
        if not templates:
            return self._result(RecognitionState.NO_GALLERY, query, quality)
        if not any(_compatible(query, item.template) for item in templates):
            return self._result(RecognitionState.INCOMPATIBLE, query, quality)

        matched = self.matcher.match(query, self.gallery)
        if _enum_value(matched.decision) != "not_evaluated":
            raise RuntimeError("matcher performed an unexpected automatic decision")
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
            if threshold is None:
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
            state,
            query,
            quality,
            best,
            second,
            margin,
            candidates,
            evaluated,
        )

    def _result(
        self,
        state: RecognitionState,
        query: BiometricEmbeddingPort,
        quality: RecognitionQuality,
        best: RecognitionCandidate | None = None,
        second: float | None = None,
        margin: float | None = None,
        candidates: tuple[RecognitionCandidate, ...] = (),
        evaluated: bool = False,
    ) -> RecognitionResult:
        return RecognitionResult(
            state,
            best,
            None if best is None else best.display_name,
            None if best is None else best.person_id,
            None if best is None else best.similarity,
            second,
            margin,
            quality,
            query.run_id,
            evaluated,
            self.policy.policy_name,
            self.policy.policy_version,
            candidates,
        )


def _compatible(query: BiometricEmbeddingPort, template: object) -> bool:
    return bool(
        query.dimension == getattr(template, "dimension")
        and query.model == getattr(template, "model")
        and query.version == getattr(template, "model_version")
        and query.weights_sha256 == getattr(template, "weights_sha256")
    )


def _safe_candidate(candidate: MatchCandidatePort) -> RecognitionCandidate:
    return RecognitionCandidate(
        candidate.identity.person_id,
        candidate.identity.display_name,
        candidate.similarity,
        candidate.rank,
    )


def _second_identity_candidate(
    candidates: tuple[MatchCandidatePort, ...],
    best: MatchCandidatePort | None,
) -> MatchCandidatePort | None:
    if best is None:
        return None
    return next(
        (
            item
            for item in candidates
            if item.identity.person_id != best.identity.person_id
        ),
        None,
    )


def _quality_allows_decision(
    query: BiometricEmbeddingPort,
    score: FaceQualityScorePort | None,
    policy: RecognitionPolicy,
) -> bool:
    alignment_quality = _enum_value(query.alignment_quality)
    if alignment_quality == "rejected":
        return False
    if alignment_quality == "low_quality" and not policy.allow_low_quality:
        return False
    if policy.minimum_quality_score is not None:
        return score is not None and score.total_score >= policy.minimum_quality_score
    return True


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))
