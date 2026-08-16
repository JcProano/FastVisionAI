"""Concrete UI-composition adapters for explicitly enabled ActionExecutor effects."""

from .detection_event_adapter import (
    DetectionEventActionAdapterError, DetectionEventServiceActionAdapter,
)
from .popup_adapter import IdentificationPopupActionAdapter
from .automatic_attendance_adapter import AutomaticAttendanceEventAdapter

__all__ = [
    "DetectionEventActionAdapterError", "DetectionEventServiceActionAdapter",
    "IdentificationPopupActionAdapter",
    "AutomaticAttendanceEventAdapter",
]
