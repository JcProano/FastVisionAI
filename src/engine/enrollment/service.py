"""Legacy facade for the explicit biometric-enrollment use case."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from src.core.biometrics.application import EnrollIdentityUseCase
from src.core.biometrics.infrastructure import (
    EngineFaceIdentityFactory,
    NumpyEmbeddingMath,
)
from src.engine.embedding.contracts import FaceEmbedding
from src.engine.gallery.gallery import FaceGallery

from .contracts import EnrollmentPolicy, EnrollmentResult


class EnrollmentService(EnrollIdentityUseCase):
    def __init__(
        self, gallery: FaceGallery, policy: EnrollmentPolicy | None = None
    ) -> None:
        super().__init__(
            gallery,
            EngineFaceIdentityFactory(),
            NumpyEmbeddingMath(),
            policy,
        )

    def enroll(
        self,
        person_id: str,
        display_name: str,
        embeddings: Sequence[FaceEmbedding],
        metadata: Mapping[str, Any] | None = None,
    ) -> EnrollmentResult:
        return self.execute(person_id, display_name, embeddings, metadata)
