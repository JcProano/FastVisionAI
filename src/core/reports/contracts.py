"""Safe, immutable contracts for local read-only reporting."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class ReportError(RuntimeError): pass
class ReportValidationError(ValueError): pass
class ReportExportError(ReportError): pass
class ReportExportUnavailableError(ReportExportError): pass


@dataclass(frozen=True, slots=True)
class ReportPolicy:
    default_range_days: int = 7
    max_rows: int = 5_000
    presentation_timezone: str = "America/Guayaquil"

    def __post_init__(self) -> None:
        if self.default_range_days <= 0 or self.max_rows <= 0:
            raise ReportValidationError("report limits must be positive")
        try: ZoneInfo(self.presentation_timezone)
        except ZoneInfoNotFoundError as exc:
            raise ReportValidationError("presentation timezone is invalid") from exc


@dataclass(frozen=True, slots=True)
class RecentDetectionDTO:
    event_type: str
    timestamp: datetime
    person_id: str | None
    display_name: str | None


@dataclass(frozen=True, slots=True)
class RecentAttendanceDTO:
    event_type: str
    timestamp: datetime
    person_id: str
    display_name: str | None


@dataclass(frozen=True, slots=True)
class DailyReportDTO:
    date: date
    registered_people: int
    active_people: int
    disabled_people: int
    pending_people: int
    detection_events: int
    registered_candidate_events: int
    unregistered_events: int
    multiple_faces_events: int
    attendance_check_ins: int
    attendance_check_outs: int
    unique_attendance_people: int
    first_attendance_at: datetime | None
    last_attendance_at: datetime | None
    rows_considered: int
    truncated: bool


@dataclass(frozen=True, slots=True)
class DateRangeDayDTO:
    date: date
    detections: int
    unique_people: int
    check_ins: int
    check_outs: int
    attendance_present: int = 0
    worked_seconds: int = 0
    late_people: int = 0
    overtime_seconds: int = 0
    incomplete_days: int = 0


@dataclass(frozen=True, slots=True)
class DateRangeReportDTO:
    date_from: date
    date_to: date
    days: tuple[DateRangeDayDTO, ...]
    rows_considered: int
    truncated: bool


@dataclass(frozen=True, slots=True)
class PersonAttendanceReportDTO:
    person_id: str
    display_name: str
    masked_cedula: str
    status: str
    date_from: date
    date_to: date
    detection_count: int
    first_detection_at: datetime | None
    last_detection_at: datetime | None
    check_ins: int
    check_outs: int
    first_attendance_at: datetime | None
    last_attendance_at: datetime | None
    rows_considered: int
    truncated: bool
    days_present: int = 0
    days_late: int = 0
    worked_seconds: int = 0
    overtime_seconds: int = 0
    incomplete_days: int = 0


@dataclass(frozen=True, slots=True)
class DetectionSummaryDTO:
    date_from: date
    date_to: date
    total: int
    registered_candidates: int
    unregistered: int
    multiple_faces: int
    incompatible: int
    unique_people: int
    latest: tuple[RecentDetectionDTO, ...]
    rows_considered: int
    truncated: bool


@dataclass(frozen=True, slots=True)
class SystemSummaryDTO:
    date: date
    registered_people: int
    active_people: int
    disabled_people: int
    pending_people: int
    detections: int
    attendance_check_ins: int
    attendance_check_outs: int
    unique_attendance_people: int
    latest_detections: tuple[RecentDetectionDTO, ...]
    latest_attendance: tuple[RecentAttendanceDTO, ...]
    rows_considered: int
    truncated: bool


class ReportFormat(str, Enum):
    CSV = "CSV"
    EXCEL = "EXCEL"
    PDF = "PDF"


@dataclass(frozen=True, slots=True)
class ReportExportResultDTO:
    success: bool
    format: ReportFormat
    display_target: str | None
    message: str
    unavailable: bool = False


@dataclass(frozen=True, slots=True)
class AttendanceDailyDetailReportDTO:
    date: date
    days: tuple[object, ...]
    rows_considered: int


@dataclass(frozen=True, slots=True)
class AttendanceMonthlyReportDTO:
    year: int
    month: int
    people: tuple[object, ...]
    rows_considered: int
