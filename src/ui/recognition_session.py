"""Experimental candidate lookup isolated from capture and presentation."""

from __future__ import annotations

from src.engine.embedding.contracts import FaceEmbedding
from src.engine.face_quality.contracts import FaceQualityScore
from src.engine.gallery import FaceGallery, FaceMatcher, MatchDecision
from src.ui.contracts import ErrorDTO, MonitoringDTO, UIErrorCode, UIState


class ExperimentalRecognitionSession:
    def __init__(self, gallery: FaceGallery, matcher: FaceMatcher) -> None:
        if matcher.policy.automatic_decision_enabled or matcher.policy.threshold is not None:
            raise ValueError("experimental UI requires automatic decisions to remain disabled")
        self.gallery = gallery
        self.matcher = matcher

    def query(
        self, embedding: FaceEmbedding, score: FaceQualityScore | None = None
    ) -> tuple[MonitoringDTO, ErrorDTO | None]:
        if not self.gallery.templates():
            return self.empty(), None
        try:
            result = self.matcher.match(embedding, self.gallery)
        except Exception:
            return self.empty(), ErrorDTO(
                UIState.ERROR, UIErrorCode.MATCHER_ERROR,
                "La comparación experimental falló; la monitorización continúa.", True,
            )
        best = result.best_candidate
        if best is None:
            return self.empty(), None
        if result.decision is not MatchDecision.NOT_EVALUATED:
            raise RuntimeError("automatic matcher decision must remain disabled")
        return MonitoringDTO(
            UIState.MONITORING, "Candidato experimental",
            best.identity.display_name, best.similarity, "NOT_EVALUATED",
            True, None if score is None else score.total_score,
            None if score is None else score.quality_band.value,
        ), None

    @staticmethod
    def empty() -> MonitoringDTO:
        return MonitoringDTO(
            UIState.MONITORING, "Sin candidatos registrados", None, None,
            "deshabilitada / NOT_EVALUATED", True,
        )
