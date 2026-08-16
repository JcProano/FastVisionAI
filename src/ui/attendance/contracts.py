"""Safe presentation-only attendance DTOs."""

from dataclasses import dataclass
from datetime import date, datetime

from src.core.attendance import AttendanceDTO


@dataclass(frozen=True, slots=True)
class AttendanceListDTO:
    events: tuple[AttendanceDTO, ...]
    total: int
    message: str


@dataclass(frozen=True, slots=True)
class AttendanceUIResult:
    success: bool
    message: str
    attendance_id: str | None = None


@dataclass(frozen=True, slots=True)
class PersonAttendanceSummaryDTO:
    last_check_in: datetime | None = None
    last_check_out: datetime | None = None
    events_today: int = 0


@dataclass(frozen=True, slots=True)
class AttendanceDayDTO:
    person_id: str
    local_date: date
    display_name: str | None
    masked_cedula: str | None
    check_in: datetime | None
    check_out: datetime | None
    worked_seconds: int
    late_seconds: int
    overtime_seconds: int
    status: str
    check_in_source: str | None
    check_out_source: str | None
    check_in_camera: str | None
    check_out_camera: str | None


@dataclass(frozen=True, slots=True)
class AttendanceDayListDTO:
    days: tuple[AttendanceDayDTO, ...]
    total: int
    message: str


@dataclass(frozen=True, slots=True)
class AttendanceDetailDTO:
    day: AttendanceDayDTO
    person: object | None
    thumbnail: object | None


@dataclass(frozen=True, slots=True)
class AttendanceDashboardDTO:
    present: int
    completed: int
    pending: int
    late: int
    latest: tuple[tuple[str, str, datetime], ...]
