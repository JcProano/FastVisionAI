"""Use case for recording an explicit manual check-in."""

from __future__ import annotations

from datetime import datetime
from typing import Callable

from ..domain.models import AttendanceEventType, AttendanceOperationResult
from ..domain.policy import AttendancePolicy
from ..domain.ports import AttendanceRepositoryPort, PersonReaderPort
from ._record_manual_attendance import _RecordManualAttendance
from ._support import utc_now


class ManualCheckInUseCase:
    def __init__(
        self,
        repository: AttendanceRepositoryPort,
        people: PersonReaderPort,
        policy: AttendancePolicy,
        *,
        utcnow: Callable[[], datetime] = utc_now,
    ) -> None:
        self._recorder = _RecordManualAttendance(
            repository, people, policy, utcnow
        )

    def execute(
        self,
        person_id: str,
        *,
        timestamp: datetime | None = None,
        camera_id: str | None = None,
        notes: str | None = None,
    ) -> AttendanceOperationResult:
        return self._recorder.execute(
            person_id,
            AttendanceEventType.MANUAL_CHECK_IN,
            timestamp=timestamp,
            camera_id=camera_id,
            notes=notes,
        )
