"""Shared implementation behind the two explicit manual attendance use cases."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Callable

from ..domain.models import (
    AttendanceEventType,
    AttendanceOperationResult,
    AttendanceQuery,
    AttendanceRecord,
)
from ..domain.policy import AttendancePolicy
from ..domain.ports import AttendanceRepositoryPort, PersonReaderPort
from ._support import is_active_person


class _RecordManualAttendance:
    def __init__(
        self,
        repository: AttendanceRepositoryPort,
        people: PersonReaderPort,
        policy: AttendancePolicy,
        utcnow: Callable[[], datetime],
    ) -> None:
        self._repository = repository
        self._people = people
        self._policy = policy
        self._utcnow = utcnow

    def execute(
        self,
        person_id: str,
        event_type: AttendanceEventType,
        *,
        timestamp: datetime | None = None,
        camera_id: str | None = None,
        notes: str | None = None,
    ) -> AttendanceOperationResult:
        if not self._policy.enabled:
            return AttendanceOperationResult(False, False, "attendance_disabled")
        if not self._policy.allow_manual_events:
            return AttendanceOperationResult(False, False, "manual_events_disabled")
        if not is_active_person(self._people, person_id):
            return AttendanceOperationResult(False, False, "person_not_active")

        moment = timestamp or self._utcnow()
        latest = self._repository.query(
            AttendanceQuery(person_id=person_id, event_type=event_type, limit=1)
        )
        if latest and (
            moment - latest[0].timestamp
        ).total_seconds() < self._policy.duplicate_event_cooldown_seconds:
            return AttendanceOperationResult(False, False, "duplicate_cooldown")

        try:
            record = AttendanceRecord(
                str(uuid.uuid4()),
                person_id,
                event_type,
                moment,
                None,
                camera_id,
                None,
                self._utcnow(),
                notes,
            )
            self._repository.create(record)
            return AttendanceOperationResult(True, True, "recorded", record)
        except Exception:
            return AttendanceOperationResult(False, False, "persistence_error")
