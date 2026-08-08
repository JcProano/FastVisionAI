"""Safe UI mapping for RecognitionService results."""

from __future__ import annotations

from src.engine.embedding.contracts import FaceEmbedding
from src.engine.face_quality.contracts import FaceQualityScore
from src.engine.gallery import FaceGallery
from src.engine.recognition import RecognitionService, RecognitionState
from src.ui.contracts import ErrorDTO, MonitoringDTO, UIErrorCode, UIState


class ExperimentalRecognitionSession:
    def __init__(self, service: RecognitionService) -> None:
        policy = service.policy
        if policy.automatic_decision_enabled:
            raise ValueError("experimental UI requires automatic decisions to remain disabled")
        if policy.match_threshold is not None:
            raise ValueError("experimental UI requires match_threshold=null")
        if policy.ambiguity_margin is not None:
            raise ValueError("experimental UI requires ambiguity_margin=null")
        self._service = service

    @property
    def gallery(self) -> FaceGallery:
        """Shared gallery reference for composition compatibility; read-only property."""
        return self._service.gallery

    def query(
        self, embedding: FaceEmbedding, score: FaceQualityScore | None = None
    ) -> tuple[MonitoringDTO, ErrorDTO | None]:
        try:
            result = self._service.recognize(embedding, score)
        except Exception:
            return self.unavailable(), ErrorDTO(
                UIState.ERROR, UIErrorCode.MATCHER_ERROR,
                "La comparación experimental falló; la monitorización continúa.", True,
            )
        if result.state is RecognitionState.NO_GALLERY:
            return self.empty(), None
        if result.state is RecognitionState.INCOMPATIBLE:
            return self.incompatible(), None
        if result.state is not RecognitionState.NOT_EVALUATED:
            return self.unavailable(), ErrorDTO(
                UIState.ERROR, UIErrorCode.MATCHER_ERROR,
                "La política experimental devolvió un estado no permitido.", True,
            )
        best = result.primary_candidate
        if best is None:
            return self.incompatible(), None
        return MonitoringDTO(
            UIState.MONITORING, "Candidato experimental",
            best.display_name, best.similarity, "NOT_EVALUATED",
            True, None if score is None else score.total_score,
            None if score is None else score.quality_band.value,
            RecognitionState.NOT_EVALUATED.name,
            best.person_id,
        ), None

    @staticmethod
    def empty() -> MonitoringDTO:
        return MonitoringDTO(
            UIState.MONITORING, "Sin candidatos registrados", None, None,
            "deshabilitada / NOT_EVALUATED", True,
            recognition_state=RecognitionState.NO_GALLERY.name,
        )

    @staticmethod
    def incompatible() -> MonitoringDTO:
        return MonitoringDTO(
            UIState.MONITORING, "Sin candidatos compatibles", None, None,
            "deshabilitada / NOT_EVALUATED", True,
            recognition_state=RecognitionState.INCOMPATIBLE.name,
        )

    @staticmethod
    def unavailable() -> MonitoringDTO:
        return MonitoringDTO(
            UIState.MONITORING, "Sin candidatos compatibles", None, None,
            "deshabilitada / NOT_EVALUATED", True,
            recognition_state=RecognitionState.NOT_EVALUATED.name,
        )
