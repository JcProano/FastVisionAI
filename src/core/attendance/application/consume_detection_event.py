"""Use case for atomically consuming one recognition event."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable
from zoneinfo import ZoneInfo

from ..domain.models import AttendanceEvaluationResult
from ..domain.policy import AttendancePolicy
from ..domain.ports import (
    AttendanceRepositoryPort,
    LocalDayClockPort,
    PersonReaderPort,
)
from ._support import is_active_person, is_canonical_uuid, utc_now


class ConsumeAttendanceDetectionUseCase:
    def __init__(
        self,
        repository: AttendanceRepositoryPort,
        people: PersonReaderPort,
        policy: AttendancePolicy,
        clock: LocalDayClockPort,
        *,
        utcnow: Callable[[], datetime] = utc_now,
    ) -> None:
        self._repository = repository
        self._people = people
        self._policy = policy
        self._clock = clock
        self._utcnow = utcnow

    def execute(
        self,
        person_id: str,
        *,
        source_event_id: str,
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
        if not is_canonical_uuid(person_id):
            return AttendanceEvaluationResult(False, None, "invalid_person_id", True)
        if not source_event_id or not str(source_event_id).strip():
            return AttendanceEvaluationResult(
                False, None, "invalid_source_event", True
            )
        if not is_active_person(self._people, person_id):
            return AttendanceEvaluationResult(False, None, "person_not_active", True)

        moment = timestamp or self._utcnow()
        if moment.tzinfo is None:
            return AttendanceEvaluationResult(False, None, "invalid_timestamp", True)
        moment = moment.astimezone(timezone.utc)
        created = self._utcnow().astimezone(timezone.utc)
        local_day = moment.astimezone(ZoneInfo(self._policy.timezone)).date()
        start, end = self._clock.local_day_utc_bounds(
            local_day, self._policy.timezone
        )
        try:
            reason, record = self._repository.consume_automatic_toggle(
                person_id=person_id,
                source_event_id=str(source_event_id),
                timestamp=moment,
                camera_id=camera_id,
                created_at=created,
                day_start=start,
                day_end=end,
                duplicate_cooldown_seconds=(
                    self._policy.duplicate_event_cooldown_seconds
                ),
                minimum_checkout_interval_seconds=(
                    self._policy.minimum_time_between_check_in_out_seconds
                ),
            )
            return AttendanceEvaluationResult(
                record is not None,
                None if record is None else record.event_type,
                reason,
                True,
                record,
            )
        except Exception:
            return AttendanceEvaluationResult(
                False, None, "persistence_error", True
            )
