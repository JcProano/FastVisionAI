"""Attendance use cases and read projections."""

from .consume_detection_event import ConsumeAttendanceDetectionUseCase
from .evaluate_observation import EvaluateAttendanceObservationUseCase
from .manual_check_in import ManualCheckInUseCase
from .manual_check_out import ManualCheckOutUseCase
from .projection import monthly_summary, project_days, today_summary

__all__ = [
    "ConsumeAttendanceDetectionUseCase",
    "EvaluateAttendanceObservationUseCase",
    "ManualCheckInUseCase",
    "ManualCheckOutUseCase",
    "monthly_summary",
    "project_days",
    "today_summary",
]
