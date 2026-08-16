"""Explicit attendance policy; automatic attendance is disabled by default."""

from dataclasses import dataclass
from datetime import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .contracts import AttendancePolicyError


@dataclass(frozen=True, slots=True)
class AttendancePolicy:
    enabled: bool = False
    automatic_attendance_enabled: bool = False
    minimum_stable_observations: int = 3
    minimum_observation_seconds: float = 2.0
    duplicate_event_cooldown_seconds: float = 60.0
    minimum_time_between_check_in_out_seconds: float = 60.0
    allow_manual_events: bool = True
    policy_name: str = "attendance_disabled"
    policy_version: str = "1.0"
    automatic_mode: str = "TOGGLE_DAILY"
    timezone: str = "America/Guayaquil"
    workday_start: str = "08:00"
    workday_end: str = "17:00"
    late_after: str = "08:10"
    overtime_after: str = "17:00"

    def __post_init__(self) -> None:
        if self.minimum_stable_observations <= 0:
            raise AttendancePolicyError("minimum observations must be positive")
        intervals = (
            self.minimum_observation_seconds,
            self.duplicate_event_cooldown_seconds,
            self.minimum_time_between_check_in_out_seconds,
        )
        if min(intervals) < 0:
            raise AttendancePolicyError("attendance intervals must be non-negative")
        if not self.policy_name.strip() or not self.policy_version.strip():
            raise AttendancePolicyError("policy provenance is required")
        if self.automatic_mode != "TOGGLE_DAILY":
            raise AttendancePolicyError("automatic attendance mode is invalid")
        try: ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise AttendancePolicyError("work schedule timezone is invalid") from exc
        parsed = tuple(_parse_time(value) for value in (
            self.workday_start, self.workday_end, self.late_after, self.overtime_after,
        ))
        if parsed[0] >= parsed[1]:
            raise AttendancePolicyError("workday_start must precede workday_end")

    @property
    def late_time(self) -> time: return _parse_time(self.late_after)

    @property
    def overtime_time(self) -> time: return _parse_time(self.overtime_after)


def _parse_time(value: str) -> time:
    try:
        parsed = time.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise AttendancePolicyError("work schedule times must use HH:MM") from exc
    if len(value) != 5 or parsed.second or parsed.microsecond:
        raise AttendancePolicyError("work schedule times must use HH:MM")
    return parsed
