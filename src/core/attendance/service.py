"""Legacy facade composing and delegating to explicit attendance use cases."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Callable

from src.core.time_provider import Clock

from .application import (
    ConsumeAttendanceDetectionUseCase,
    EvaluateAttendanceObservationUseCase,
    ManualCheckInUseCase,
    ManualCheckOutUseCase,
)
from .application._support import utc_now
from .domain.models import AttendanceEvaluationResult, AttendanceOperationResult
from .domain.policy import AttendancePolicy
from .domain.ports import (
    AttendanceRepositoryPort,
    LocalDayClockPort,
    PersonReaderPort,
)


class AttendanceService:
    """Preserves the legacy API while consumers migrate to individual use cases."""

    def __init__(
        self,
        repository: AttendanceRepositoryPort,
        people: PersonReaderPort,
        policy: AttendancePolicy,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        utcnow: Callable[[], datetime] = utc_now,
        clock: LocalDayClockPort | None = None,
    ) -> None:
        self.repository = repository
        self.people = people
        self.policy = policy
        resolved_clock = clock or Clock()
        self._manual_check_in = ManualCheckInUseCase(
            repository, people, policy, utcnow=utcnow
        )
        self._manual_check_out = ManualCheckOutUseCase(
            repository, people, policy, utcnow=utcnow
        )
        self._evaluate_observation = EvaluateAttendanceObservationUseCase(
            repository,
            people,
            policy,
            monotonic=monotonic,
            utcnow=utcnow,
        )
        self._consume_detection = ConsumeAttendanceDetectionUseCase(
            repository,
            people,
            policy,
            resolved_clock,
            utcnow=utcnow,
        )

    def manual_check_in(
        self,
        person_id: str,
        *,
        timestamp: datetime | None = None,
        camera_id: str | None = None,
        notes: str | None = None,
    ) -> AttendanceOperationResult:
        return self._manual_check_in.execute(
            person_id,
            timestamp=timestamp,
            camera_id=camera_id,
            notes=notes,
        )

    def manual_check_out(
        self,
        person_id: str,
        *,
        timestamp: datetime | None = None,
        camera_id: str | None = None,
        notes: str | None = None,
    ) -> AttendanceOperationResult:
        return self._manual_check_out.execute(
            person_id,
            timestamp=timestamp,
            camera_id=camera_id,
            notes=notes,
        )

    def evaluate_observation(
        self,
        person_id: str,
        *,
        source_event_id: str | None = None,
        camera_id: str | None = None,
        timestamp: datetime | None = None,
    ) -> AttendanceEvaluationResult:
        return self._evaluate_observation.execute(
            person_id,
            source_event_id=source_event_id,
            camera_id=camera_id,
            timestamp=timestamp,
        )

    def consume_detection_event(
        self,
        person_id: str,
        *,
        source_event_id: str,
        camera_id: str | None = None,
        timestamp: datetime | None = None,
    ) -> AttendanceEvaluationResult:
        return self._consume_detection.execute(
            person_id,
            source_event_id=source_event_id,
            camera_id=camera_id,
            timestamp=timestamp,
        )
