"""Use case for evaluating stable recognition observations."""

from __future__ import annotations

import time
import uuid
from datetime import datetime
from typing import Callable

from ..domain.models import AttendanceEvaluationResult, AttendanceRecord
from ..domain.policy import AttendancePolicy
from ..domain.ports import AttendanceRepositoryPort, PersonReaderPort
from ._support import is_active_person, next_automatic_event, utc_now


class EvaluateAttendanceObservationUseCase:
    def __init__(
        self,
        repository: AttendanceRepositoryPort,
        people: PersonReaderPort,
        policy: AttendancePolicy,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        utcnow: Callable[[], datetime] = utc_now,
    ) -> None:
        self._repository = repository
        self._people = people
        self._policy = policy
        self._monotonic = monotonic
        self._utcnow = utcnow
        self._observations: dict[str, tuple[float, int]] = {}

    def execute(
        self,
        person_id: str,
        *,
        source_event_id: str | None = None,
        camera_id: str | None = None,
        timestamp: datetime | None = None,
    ) -> AttendanceEvaluationResult:
        if not self._policy.enabled:
            return AttendanceEvaluationResult(
                False, None, "attendance_disabled", False
            )
        if not self._policy.automatic_attendance_enabled:
            return AttendanceEvaluationResult(
                False, None, "automatic_attendance_disabled", False
            )
        if not is_active_person(self._people, person_id):
            return AttendanceEvaluationResult(
                False, None, "person_not_active", True
            )

        now = self._monotonic()
        first, count = self._observations.get(person_id, (now, 0))
        count += 1
        self._observations[person_id] = (first, count)
        latest = self._repository.latest_for_person(person_id)
        proposed = next_automatic_event(latest.event_type if latest else None)
        if (
            count < self._policy.minimum_stable_observations
            or now - first < self._policy.minimum_observation_seconds
        ):
            return AttendanceEvaluationResult(
                False, proposed, "observation_not_stable", True
            )

        moment = timestamp or self._utcnow()
        if latest and (
            moment - latest.timestamp
        ).total_seconds() < self._policy.minimum_time_between_check_in_out_seconds:
            return AttendanceEvaluationResult(
                False, proposed, "minimum_interval", True
            )

        try:
            record = AttendanceRecord(
                str(uuid.uuid4()),
                person_id,
                proposed,
                moment,
                source_event_id,
                camera_id,
                None,
                self._utcnow(),
            )
            self._repository.create(record)
            self._observations.pop(person_id, None)
            return AttendanceEvaluationResult(
                True, proposed, "recorded", True, record
            )
        except Exception:
            return AttendanceEvaluationResult(
                False, proposed, "persistence_error", True
            )
