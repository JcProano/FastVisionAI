"""In-memory test doubles for attendance application tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

from src.core.attendance.domain.models import (
    AttendanceDailySummary,
    AttendanceEventType,
    AttendanceQuery,
    AttendanceRecord,
)
from src.core.attendance.domain.policy import AttendancePolicy


@dataclass(frozen=True)
class FakePerson:
    status: str


class FakePeopleReader:
    def __init__(self, statuses: dict[str, str]) -> None:
        self._statuses = statuses
        self.calls: list[str] = []

    def get_by_person_id(self, person_id: str) -> FakePerson | None:
        self.calls.append(person_id)
        status = self._statuses.get(person_id)
        return None if status is None else FakePerson(status)


class InMemoryAttendanceRepository:
    def __init__(self, records: list[AttendanceRecord] | None = None) -> None:
        self.records = list(records or [])
        self.fail_on_create = False
        self.fail_on_toggle = False
        self.toggle_result: tuple[str, AttendanceRecord | None] = ("ignored", None)
        self.toggle_calls: list[dict[str, object]] = []

    def create(self, item: AttendanceRecord) -> AttendanceRecord:
        if self.fail_on_create:
            raise RuntimeError("simulated persistence failure")
        self.records.append(item)
        return item

    def query(self, query: AttendanceQuery) -> tuple[AttendanceRecord, ...]:
        matches = [
            record
            for record in self.records
            if (query.person_id is None or record.person_id == query.person_id)
            and (query.event_type is None or record.event_type == query.event_type)
        ]
        matches.sort(key=lambda record: record.timestamp, reverse=True)
        return tuple(matches[query.offset : query.offset + query.limit])

    def latest_for_person(self, person_id: str) -> AttendanceRecord | None:
        matches = [
            record for record in self.records if record.person_id == person_id
        ]
        return max(matches, key=lambda record: record.timestamp, default=None)

    def consume_automatic_toggle(
        self, **arguments: object
    ) -> tuple[str, AttendanceRecord | None]:
        self.toggle_calls.append(arguments)
        if self.fail_on_toggle:
            raise RuntimeError("simulated atomic persistence failure")
        return self.toggle_result

    def daily_summary(self, day: date) -> AttendanceDailySummary:
        raise NotImplementedError


class FixedLocalDayClock:
    def __init__(self, start: datetime, end: datetime) -> None:
        self.start = start
        self.end = end
        self.calls: list[tuple[date, str]] = []

    def local_day_utc_bounds(
        self, day: date, timezone_name: str
    ) -> tuple[datetime, datetime]:
        self.calls.append((day, timezone_name))
        return self.start, self.end


def enabled_policy(**changes: object) -> AttendancePolicy:
    values: dict[str, object] = {
        "enabled": True,
        "automatic_attendance_enabled": True,
        "minimum_stable_observations": 2,
        "minimum_observation_seconds": 1,
        "duplicate_event_cooldown_seconds": 60,
        "minimum_time_between_check_in_out_seconds": 30,
        "allow_manual_events": True,
        "policy_name": "unit-test",
        "policy_version": "1",
    }
    values.update(changes)
    return AttendancePolicy(**values)


def attendance_record(
    person_id: str,
    event_type: AttendanceEventType,
    timestamp: datetime,
    *,
    source_event_id: str | None = None,
) -> AttendanceRecord:
    return AttendanceRecord(
        attendance_id=f"record-{len(person_id)}-{event_type.value}",
        person_id=person_id,
        event_type=event_type,
        timestamp=timestamp,
        source_event_id=source_event_id,
        camera_id=None,
        session_id=None,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
