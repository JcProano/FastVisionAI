"""Controlled, adapter-only execution of application action proposals."""

from .adapters import (
    CallbackDetectionEventActionAdapter, CallbackPopupActionAdapter,
    DetectionEventActionAdapter, PopupActionAdapter,
)
from .contracts import (
    ActionExecutionContext, ActionExecutionInput, ActionExecutionResult,
    ActionExecutionState, ActionExecutorValidationError, ExecutableAction,
    DetectionEventActionData,
    PopupActionData,
)
from .executor import ActionExecutor
from .policy import ActionExecutorPolicy

__all__ = [
    "ActionExecutionContext", "ActionExecutionInput", "ActionExecutionResult",
    "ActionExecutionState", "ActionExecutor", "ActionExecutorPolicy",
    "ActionExecutorValidationError", "CallbackDetectionEventActionAdapter",
    "CallbackPopupActionAdapter", "DetectionEventActionAdapter", "ExecutableAction",
    "PopupActionAdapter", "DetectionEventActionData", "PopupActionData",
]
