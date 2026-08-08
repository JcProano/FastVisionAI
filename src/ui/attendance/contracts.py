"""Safe presentation-only attendance DTOs."""

from dataclasses import dataclass
from datetime import datetime

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
