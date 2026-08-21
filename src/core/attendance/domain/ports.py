"""Ports owned by the attendance domain/application boundary."""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol

from .models import (
    AttendanceDailySummary,
    AttendanceQuery,
    AttendanceRecord,
)


class PersonRecordPort(Protocol):
    """Minimal civil-person view required by attendance rules."""

    @property
    def status(self) -> object: ...


class PersonReaderPort(Protocol):
    """Read port that prevents application code from depending on SQLite people."""

    def get_by_person_id(self, person_id: str) -> PersonRecordPort | None: ...


class AttendanceRepositoryPort(Protocol):
    """Persistence operations required by attendance use cases."""

    def create(self, item: AttendanceRecord) -> AttendanceRecord: ...

    def query(self, query: AttendanceQuery) -> tuple[AttendanceRecord, ...]: ...

    def latest_for_person(self, person_id: str) -> AttendanceRecord | None: ...

    def consume_automatic_toggle(
        self,
        *,
        person_id: str,
        source_event_id: str,
        timestamp: datetime,
        camera_id: str | None,
        created_at: datetime,
        day_start: datetime,
        day_end: datetime,
        duplicate_cooldown_seconds: float,
        minimum_checkout_interval_seconds: float,
    ) -> tuple[str, AttendanceRecord | None]: ...

    def daily_summary(self, day: date) -> AttendanceDailySummary: ...


class LocalDayClockPort(Protocol):
    """Time-boundary port used to calculate a local day in UTC."""

    def local_day_utc_bounds(
        self, day: date, timezone_name: str
    ) -> tuple[datetime, datetime]: ...
