"""Safe administrative attendance contracts (no civil or biometric payloads)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum


class AttendanceValidationError(ValueError):
    pass


class AttendanceRepositoryError(RuntimeError):
    pass


class AttendancePersistenceError(RuntimeError):
    pass


class AttendancePolicyError(ValueError):
    pass


class AttendanceEventType(str, Enum):
    CHECK_IN = "CHECK_IN"
    CHECK_OUT = "CHECK_OUT"
    MANUAL_CHECK_IN = "MANUAL_CHECK_IN"
    MANUAL_CHECK_OUT = "MANUAL_CHECK_OUT"


@dataclass(frozen=True, slots=True)
class AttendanceRecord:
    attendance_id: str
    person_id: str
    event_type: AttendanceEventType
    timestamp: datetime
    source_event_id: str | None
    camera_id: str | None
    session_id: str | None
    created_at: datetime
    notes: str | None = None

    def __post_init__(self) -> None:
        if not self.attendance_id.strip() or not self.person_id.strip():
            raise AttendanceValidationError("attendance_id and person_id are required")
        if not isinstance(self.event_type, AttendanceEventType):
            raise AttendanceValidationError("event_type is invalid")
        if self.timestamp.tzinfo is None or self.created_at.tzinfo is None:
            raise AttendanceValidationError("attendance timestamps must be timezone-aware")
        if self.notes is not None:
            cleaned = self.notes.strip()
            if len(cleaned) > 500 or any(
                ord(character) < 32 and character not in "\n\t" for character in cleaned
            ):
                raise AttendanceValidationError("attendance notes are invalid")
            object.__setattr__(self, "notes", cleaned or None)


@dataclass(frozen=True, slots=True)
class AttendanceDTO:
    attendance_id: str
    person_id: str
    display_name: str | None
    masked_cedula: str | None
    event_type: str
    timestamp: datetime
    camera_id: str | None
    source_event_id: str | None
    notes: str | None


@dataclass(frozen=True, slots=True)
class AttendanceQuery:
    date_from: datetime | None = None
    date_to: datetime | None = None
    person_id: str | None = None
    event_type: AttendanceEventType | None = None
    limit: int = 100
    offset: int = 0

    def __post_init__(self) -> None:
        if not 1 <= self.limit <= 500 or self.offset < 0:
            raise AttendanceValidationError("query bounds invalid")
        if self.date_from and self.date_from.tzinfo is None:
            raise AttendanceValidationError("date_from must be timezone-aware")
        if self.date_to and self.date_to.tzinfo is None:
            raise AttendanceValidationError("date_to must be timezone-aware")
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise AttendanceValidationError("date range invalid")


@dataclass(frozen=True, slots=True)
class AttendanceDailySummary:
    date: date
    total_check_ins: int
    total_check_outs: int
    unique_people: int
    first_event_at: datetime | None
    last_event_at: datetime | None


@dataclass(frozen=True, slots=True)
class AttendanceOperationResult:
    success: bool
    recorded: bool
    reason: str
    record: AttendanceRecord | None = None


@dataclass(frozen=True, slots=True)
class AttendanceEvaluationResult:
    eligible: bool
    proposed_event_type: AttendanceEventType | None
    reason: str
    evaluated: bool
    record: AttendanceRecord | None = None
