"""Public attendance API with clean-architecture compatibility exports."""

from .application import (
    ConsumeAttendanceDetectionUseCase,
    EvaluateAttendanceObservationUseCase,
    ManualCheckInUseCase,
    ManualCheckOutUseCase,
    monthly_summary,
    project_days,
    today_summary,
)
from .domain.models import *
from .domain.policy import AttendancePolicy
from .domain.ports import AttendanceRepositoryPort, LocalDayClockPort, PersonReaderPort
from .infrastructure import SQLiteAttendanceRepository
from .service import AttendanceService
from .container import AttendanceComponents, AttendanceContainer

# Temporary compatibility name used by existing composition and tests.
AttendanceRepository = SQLiteAttendanceRepository
