"""Composition container for attendance application dependencies."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from .domain.policy import AttendancePolicy
from .infrastructure import SQLiteAttendanceRepository
from .service import AttendanceService

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AttendanceComponents:
    repository: object
    service: AttendanceService


class AttendanceContainer:
    @staticmethod
    def build(
        settings: dict[str, object],
        people,
        project_root: Path,
        *,
        repository_type=SQLiteAttendanceRepository,
        service_type=AttendanceService,
    ) -> AttendanceComponents | None:
        configuration = settings.get("attendance", {})
        if not isinstance(configuration, dict):
            raise ValueError("attendance configuration must be an object")
        if not bool(configuration.get("enabled", False)) or people is None:
            return None
        if (
            settings.get("profile_name") == "local_face_validation_prod"
            and bool(
                configuration.get("automatic_attendance_enabled", False)
            )
            and not isinstance(configuration.get("work_schedule"), dict)
        ):
            raise ValueError(
                "production automatic attendance requires explicit work_schedule"
            )
        configured = Path(
            str(
                configuration.get(
                    "database_path", "data/fastvision/attendance.db"
                )
            )
        )
        if configured.is_absolute():
            raise ValueError("attendance database path must be relative")
        root = project_root.resolve()
        resolved = (root / configured).resolve()
        if root not in resolved.parents:
            raise ValueError("attendance database path escapes project root")
        repository = repository_type(
            resolved,
            timeout=float(configuration.get("timeout_seconds", 5.0)),
        )
        try:
            repository.initialize()
        except Exception:
            LOGGER.warning(
                "Attendance initialization failed; attendance remains disabled"
            )
            return None
        schedule = configuration.get("work_schedule") or {}
        policy = AttendancePolicy(
            enabled=True,
            automatic_attendance_enabled=bool(
                configuration.get("automatic_attendance_enabled", False)
            ),
            minimum_stable_observations=int(
                configuration.get("minimum_stable_observations", 3)
            ),
            minimum_observation_seconds=float(
                configuration.get("minimum_observation_seconds", 2)
            ),
            duplicate_event_cooldown_seconds=float(
                configuration.get("duplicate_event_cooldown_seconds", 60)
            ),
            minimum_time_between_check_in_out_seconds=float(
                configuration.get(
                    "minimum_time_between_check_in_out_seconds", 60
                )
            ),
            allow_manual_events=bool(
                configuration.get("allow_manual_events", True)
            ),
            policy_name=str(
                configuration.get(
                    "policy_name", "attendance_manual_validation"
                )
            ),
            policy_version=str(configuration.get("policy_version", "1.0")),
            automatic_mode=str(
                configuration.get("automatic_mode", "TOGGLE_DAILY")
            ),
            timezone=str(schedule.get("timezone", "America/Guayaquil")),
            workday_start=str(schedule.get("workday_start", "08:00")),
            workday_end=str(schedule.get("workday_end", "17:00")),
            late_after=str(schedule.get("late_after", "08:10")),
            overtime_after=str(schedule.get("overtime_after", "17:00")),
        )
        return AttendanceComponents(
            repository, service_type(repository, people, policy)
        )
