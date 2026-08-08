"""Explicit attendance policy; automatic attendance is disabled by default."""

from dataclasses import dataclass

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
