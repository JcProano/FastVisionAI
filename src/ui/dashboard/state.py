"""Ephemeral dashboard projection; never a source of application truth."""

from __future__ import annotations

import time
from collections import deque
from datetime import datetime, timezone
from typing import Callable

from src.ui.contracts import (
    EnrollmentProgressDTO, EnrollmentResultDTO, ErrorDTO, MonitoringDTO, RuntimeStatusDTO,
)
from src.ui.people.contracts import PeopleOperationResultDTO

from .contracts import (
    DashboardEventDTO, DashboardGalleryDTO, DashboardMetricsDTO,
    DashboardQualityDTO, DashboardRecognitionDTO, DashboardSystemDTO,
)


class DashboardStateStore:
    """Bounded in-memory projection of safe UI events."""

    def __init__(
        self, history_limit: int = 100, debounce_seconds: float = 2.0, *,
        monotonic: Callable[[], float] = time.monotonic,
        utcnow: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        if history_limit <= 0 or debounce_seconds < 0:
            raise ValueError("history_limit must be positive and debounce non-negative")
        self.history_limit = history_limit
        self.debounce_seconds = debounce_seconds
        self._monotonic = monotonic
        self._utcnow = utcnow
        self.system = DashboardSystemDTO()
        self.metrics = DashboardMetricsDTO()
        self.recognition = DashboardRecognitionDTO()
        self.gallery = DashboardGalleryDTO()
        self.quality = DashboardQualityDTO()
        self._history: deque[DashboardEventDTO] = deque(maxlen=history_limit)
        self._last_key: tuple[object, ...] | None = None
        self._last_recorded = float("-inf")
        self._enrolling = False

    @property
    def history(self) -> tuple[DashboardEventDTO, ...]:
        return tuple(self._history)

    def update_metrics(self, value: DashboardMetricsDTO) -> None:
        self.metrics = value

    def update_quality(self, value: DashboardQualityDTO) -> None:
        self.quality = value

    def update_gallery(self, value: DashboardGalleryDTO) -> None:
        self.gallery = value

    def consume(self, event: object) -> None:
        if isinstance(event, RuntimeStatusDTO):
            self.system = DashboardSystemDTO(
                event.camera_state, event.runtime_state, event.detector_model_state,
                event.embedding_model_state, self.system.recognition_state,
            )
            return
        if isinstance(event, MonitoringDTO):
            self.recognition = DashboardRecognitionDTO(
                event.message, event.candidate_display_name, event.similarity,
                event.recognition_state,
                "EVALUATED" if event.evaluated else "NOT_EVALUATED",
                event.candidate_person_id,
            )
            self.system = DashboardSystemDTO(
                self.system.camera_state, self.system.runtime_state, self.system.yunet_state,
                self.system.arcface_state, event.recognition_state,
            )
            self._enrolling = False
            if event.recognition_state in {"NO_GALLERY", "INCOMPATIBLE"}:
                event_type = event.recognition_state.lower()
            elif event.candidate_display_name:
                event_type = "candidate"
            else:
                event_type = "candidate_disappeared"
            self._record(event_type, event.message, event.candidate_display_name,
                         event.similarity, event.quality_score)
            return
        if isinstance(event, EnrollmentProgressDTO):
            if not self._enrolling:
                self._record("enrollment_started", "Captura guiada iniciada")
            self._enrolling = True
            return
        if isinstance(event, EnrollmentResultDTO):
            self._enrolling = False
            self._record("enrollment_finished", event.message, event.display_name,
                         quality_score=event.average_quality)
            return
        if isinstance(event, ErrorDTO):
            self._record("recoverable_error" if event.recoverable else "error", event.message)
            return
        if isinstance(event, PeopleOperationResultDTO):
            self._record("people_operation", event.message)

    def _record(
        self, event_type: str, message: str, display_name: str | None = None,
        similarity: float | None = None, quality_score: float | None = None,
    ) -> None:
        key = (event_type, message, display_name)
        now = self._monotonic()
        if key == self._last_key and now - self._last_recorded < self.debounce_seconds:
            return
        self._history.append(DashboardEventDTO(
            self._utcnow(), event_type, display_name, similarity, quality_score, message,
        ))
        self._last_key = key
        self._last_recorded = now
