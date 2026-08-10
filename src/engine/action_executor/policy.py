"""Explicit safety policy for action execution."""

from dataclasses import dataclass

from .contracts import ActionExecutorValidationError


@dataclass(frozen=True, slots=True)
class ActionExecutorPolicy:
    enabled: bool = True
    automatic_execution_enabled: bool = False
    allow_registered_popup: bool = True
    allow_unregistered_popup: bool = True
    allow_detection_event_logging: bool = True
    allow_attendance_execution: bool = False
    require_orchestrator_actions_enabled: bool = True
    policy_name: str = "action_executor_development"
    policy_version: str = "1.0"

    def __post_init__(self) -> None:
        if not self.policy_name.strip() or not self.policy_version.strip():
            raise ActionExecutorValidationError("policy provenance is required")
        if self.allow_attendance_execution:
            raise ActionExecutorValidationError(
                "attendance execution is unavailable in Action Executor phase 27"
            )

