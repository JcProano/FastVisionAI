"""Cancelable UI enrollment workflow with post-commit optional persistence."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Sequence
from pathlib import Path

from src.engine.embedding.contracts import FaceEmbedding
from src.engine.enrollment import EnrollmentService, EnrollmentStatus
from src.engine.face_quality.contracts import FaceQualityScore
from src.engine.gallery import FaceGallery
from src.ui.contracts import (
    EnrollmentProgressDTO, EnrollmentResultDTO, RegistrationFormData, UIState,
)
from src.ui.people.controller import record_template_quality_scores

LOGGER = logging.getLogger(__name__)
PersistenceCallback = Callable[[FaceGallery, Path, Path], None]


class EnrollmentAlreadyActiveError(RuntimeError):
    pass


class LocalEnrollmentWorkflow:
    def __init__(self, gallery: FaceGallery, enrollment: EnrollmentService,
                 target_samples: int = 5) -> None:
        if target_samples <= 0:
            raise ValueError("target_samples must be positive")
        self.gallery = gallery
        self.enrollment = enrollment
        self.target_samples = target_samples
        self._lock = threading.RLock()
        self._active = False
        self._form: RegistrationFormData | None = None
        self._embeddings: list[FaceEmbedding] = []
        self._scores: list[FaceQualityScore | None] = []

    @property
    def active(self) -> bool:
        with self._lock:
            return self._active

    def start(self, form: RegistrationFormData) -> EnrollmentProgressDTO:
        with self._lock:
            if self._active:
                raise EnrollmentAlreadyActiveError("ya existe un registro activo")
            if not form.consent_confirmed:
                raise ValueError("consentimiento requerido")
            self._active = True
            self._form = form
            self._embeddings.clear()
            self._scores.clear()
            return self.progress("Mire al frente", ())

    def add_accepted_sample(
        self, embedding: FaceEmbedding, score: FaceQualityScore | None,
        instruction: str,
    ) -> EnrollmentProgressDTO:
        with self._lock:
            self._require_active()
            self._embeddings.append(embedding)
            self._scores.append(score)
            return self.progress(instruction, ())

    def progress(self, instruction: str, reasons: Sequence[str]) -> EnrollmentProgressDTO:
        scores = [item.total_score for item in self._scores if item is not None]
        latest = self._scores[-1] if self._scores else None
        return EnrollmentProgressDTO(
            UIState.ENROLLING, instruction, len(self._embeddings), self.target_samples,
            tuple(reasons), None if latest is None else latest.total_score,
            None if latest is None else latest.quality_band.value, True,
        )

    def cancel(self) -> None:
        with self._lock:
            self._discard()

    def finish(
        self,
        *,
        persistence: PersistenceCallback | None = None,
        manifest_path: Path | None = None,
        archive_path: Path | None = None,
        defer_persistence: bool = False,
        minimal_identity_metadata: bool = False,
    ) -> EnrollmentResultDTO:
        with self._lock:
            self._require_active()
            form = self._form
            embeddings = tuple(self._embeddings)
            scores = tuple(self._scores)
            assert form is not None
            identity_metadata = {} if minimal_identity_metadata else {
                    "first_name": form.first_name, "last_name": form.last_name,
                    "external_identifier": form.external_identifier,
                }
            result = self.enrollment.enroll(
                form.person_id, form.display_name, embeddings,
                metadata=identity_metadata,
            )
            accepted_indices = tuple(item.input_index for item in result.accepted_templates)
            accepted_scores = [scores[index].total_score for index in accepted_indices
                               if scores[index] is not None]
            enrolled = result.status is EnrollmentStatus.ENROLLED
            if enrolled:
                quality_scores = tuple(
                    (accepted.gallery_template_index, scores[accepted.input_index])
                    for accepted in result.accepted_templates
                    if accepted.gallery_template_index is not None
                    and scores[accepted.input_index] is not None
                )
                if quality_scores:
                    try:
                        record_template_quality_scores(
                            self.gallery, form.person_id, quality_scores  # type: ignore[arg-type]
                        )
                    except Exception:
                        LOGGER.exception(
                            "Could not attach safe quality metadata after enrollment; "
                            "biometric payload omitted"
                        )
            persistence_succeeded: bool | None = None
            message = "Registro rechazado"
            if enrolled:
                message = "Registro en memoria completado"
                if form.persist_locally and not defer_persistence:
                    if persistence is None or manifest_path is None or archive_path is None:
                        persistence_succeeded = False
                        message += "; persistencia local no configurada"
                    else:
                        try:
                            # Persistence is strictly after EnrollmentService committed the gallery.
                            persistence(self.gallery, manifest_path, archive_path)
                            persistence_succeeded = True
                            message += "; persistencia local completada"
                        except Exception:
                            persistence_succeeded = False
                            message += "; persistencia local falló, la galería en memoria continúa válida"
                            LOGGER.exception(
                                "Local gallery persistence failed after successful enrollment; "
                                "person_id=%s", form.person_id,
                            )
            dto = EnrollmentResultDTO(
                UIState.ENROLLMENT_COMPLETE if enrolled else UIState.ENROLLMENT_REJECTED,
                form.person_id, form.first_name, form.last_name, form.display_name,
                len(result.accepted_templates), len(result.rejected_templates),
                _mean(accepted_scores), min(accepted_scores) if accepted_scores else 0.0,
                max(accepted_scores) if accepted_scores else 0.0, result.status.value,
                form.persist_locally, persistence_succeeded, message,
            )
            self._discard()
            return dto

    def commit_biometric(
        self, *, minimal_identity_metadata: bool = False,
    ) -> EnrollmentResultDTO:
        """Commit only EnrollmentService/FaceGallery; all file IO remains deferred."""
        return self.finish(
            defer_persistence=True,
            minimal_identity_metadata=minimal_identity_metadata,
        )

    def _require_active(self) -> None:
        if not self._active:
            raise RuntimeError("no existe un workflow de registro activo")

    def _discard(self) -> None:
        self._embeddings.clear()
        self._scores.clear()
        self._form = None
        self._active = False


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0
