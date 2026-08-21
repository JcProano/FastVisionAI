"""Legacy facade for the explicit face-recognition use case."""

from __future__ import annotations

from src.core.biometrics.application import RecognizeFaceUseCase
from src.engine.embedding.contracts import FaceEmbedding
from src.engine.face_quality.contracts import FaceQualityScore
from src.engine.gallery import FaceGallery, FaceMatcher

from .contracts import RecognitionPolicy, RecognitionResult


class RecognitionService(RecognizeFaceUseCase):
    def __init__(
        self,
        gallery: FaceGallery,
        matcher: FaceMatcher,
        policy: RecognitionPolicy | None = None,
    ) -> None:
        super().__init__(gallery, matcher, policy)

    def recognize(
        self,
        query: FaceEmbedding,
        quality_score: FaceQualityScore | None = None,
    ) -> RecognitionResult:
        return self.execute(query, quality_score)
