"""Thread-safe state coordinator for the local UI."""

from __future__ import annotations

import threading
from pathlib import Path

from src.engine.embedding.contracts import FaceEmbedding
from src.engine.face_quality.contracts import FaceQualityScore
from src.ui.contracts import (
    EnrollmentProgressDTO, EnrollmentResultDTO, ErrorDTO, MonitoringDTO,
    RegistrationFormData, UIState,
)
from src.ui.enrollment_workflow import LocalEnrollmentWorkflow, PersistenceCallback
from src.ui.recognition_session import ExperimentalRecognitionSession


class LocalFaceUIController:
    def __init__(self, monitoring: ExperimentalRecognitionSession,
                 enrollment: LocalEnrollmentWorkflow) -> None:
        self.monitoring = monitoring
        self.enrollment = enrollment
        self._state = UIState.MONITORING
        self._lock = threading.RLock()

    @property
    def state(self) -> UIState:
        with self._lock:
            return self._state

    def monitor(self, embedding: FaceEmbedding,
                score: FaceQualityScore | None = None) -> tuple[MonitoringDTO, ErrorDTO | None]:
        with self._lock:
            if self.enrollment.active:
                return MonitoringDTO(
                    UIState.ENROLLING, "Registro guiado en curso", None, None,
                    "deshabilitada / NOT_EVALUATED", False,
                ), None
            dto, error = self.monitoring.query(embedding, score)
            self._state = UIState.MONITORING
            return dto, error

    def begin_enrollment(self, form: RegistrationFormData) -> EnrollmentProgressDTO:
        with self._lock:
            progress = self.enrollment.start(form)
            self._state = UIState.ENROLLING
            return progress

    def add_enrollment_sample(
        self, embedding: FaceEmbedding, score: FaceQualityScore | None, instruction: str,
    ) -> EnrollmentProgressDTO:
        with self._lock:
            return self.enrollment.add_accepted_sample(embedding, score, instruction)

    def finish_enrollment(
        self, *, persistence: PersistenceCallback | None = None,
        manifest_path: Path | None = None, archive_path: Path | None = None,
    ) -> EnrollmentResultDTO:
        with self._lock:
            result = self.enrollment.finish(
                persistence=persistence, manifest_path=manifest_path,
                archive_path=archive_path,
            )
            self._state = result.state
            return result

    def cancel_enrollment(self) -> None:
        with self._lock:
            self.enrollment.cancel()
            self._state = UIState.CANCELLED

    def close(self) -> None:
        with self._lock:
            if self.enrollment.active:
                self.enrollment.cancel()
            self._state = UIState.CLOSED
