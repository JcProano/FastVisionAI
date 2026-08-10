"""Concrete UI-composition adapters for explicitly enabled ActionExecutor effects."""

from .detection_event_adapter import (
    DetectionEventActionAdapterError, DetectionEventServiceActionAdapter,
)

__all__ = ["DetectionEventActionAdapterError", "DetectionEventServiceActionAdapter"]
