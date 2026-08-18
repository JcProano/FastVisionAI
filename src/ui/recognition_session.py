"""Safe UI mapping for RecognitionService results."""

from __future__ import annotations

from src.engine.embedding.contracts import FaceEmbedding
from src.engine.face_quality.contracts import FaceQualityScore
from src.engine.gallery import FaceGallery
from src.engine.recognition import RecognitionService, RecognitionState
from src.ui.contracts import ErrorDTO, MonitoringDTO, UIErrorCode, UIState


class ExperimentalRecognitionSession:
    def __init__(self, service: RecognitionService, *, calibration_invalid: bool = False) -> None:
        self._service = service
        self._calibration_invalid = calibration_invalid

    @property
    def gallery(self) -> FaceGallery:
        """Shared gallery reference for composition compatibility; read-only property."""
        return self._service.gallery

    def query(
        self, embedding: FaceEmbedding, score: FaceQualityScore | None = None
    ) -> tuple[MonitoringDTO, ErrorDTO | None]:
        if self._calibration_invalid:
            return self.unavailable(), None
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
        best = result.primary_candidate
        if result.state is RecognitionState.UNKNOWN:
            return MonitoringDTO(
                UIState.MONITORING, "PERSONA NO REGISTRADA", None, result.similarity,
                "EVALUATED", True, None if score is None else score.total_score,
                None if score is None else score.quality_band.value, "UNKNOWN", None,
                result.evaluated, self._service.policy.match_threshold,
            ), None
        if best is None:
            return self.unavailable(), None
        message = {
            RecognitionState.NOT_EVALUATED:
                "CANDIDATO DETECTADO — RECONOCIMIENTO AÚN NO CALIBRADO",
            RecognitionState.MATCH: "IDENTIFICADO",
            RecognitionState.AMBIGUOUS: "COINCIDENCIA AMBIGUA",
        }[result.state]
        return MonitoringDTO(
            UIState.MONITORING, message,
            best.display_name, best.similarity,
            "EVALUATED" if result.evaluated else "NOT_EVALUATED",
            True, None if score is None else score.total_score,
            None if score is None else score.quality_band.value,
            result.state.name, best.person_id, result.evaluated,
            self._service.policy.match_threshold,
        ), None

    @staticmethod
    def empty() -> MonitoringDTO:
        return MonitoringDTO(
            UIState.MONITORING, "GALERÍA VACÍA", None, None,
            "deshabilitada / NOT_EVALUATED", True,
            recognition_state=RecognitionState.NO_GALLERY.name,
            evaluated=False,
        )

    @staticmethod
    def incompatible() -> MonitoringDTO:
        return MonitoringDTO(
            UIState.MONITORING, "MODELO BIOMÉTRICO INCOMPATIBLE", None, None,
            "deshabilitada / NOT_EVALUATED", True,
            recognition_state=RecognitionState.INCOMPATIBLE.name,
            evaluated=False,
        )

    @staticmethod
    def unavailable() -> MonitoringDTO:
        return MonitoringDTO(
            UIState.MONITORING, "RECONOCIMIENTO DESACTIVADO — CALIBRACIÓN INVÁLIDA", None, None,
            "deshabilitada / NOT_EVALUATED", True,
            recognition_state=RecognitionState.NOT_EVALUATED.name,
            evaluated=False,
        )
