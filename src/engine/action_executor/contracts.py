"""Safe contracts for controlled execution of orchestrator proposals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import math


class ActionExecutorValidationError(ValueError):
    pass


class ExecutableAction(str, Enum):
    SHOW_REGISTERED_POPUP = "SHOW_REGISTERED_POPUP"
    SHOW_UNREGISTERED_POPUP = "SHOW_UNREGISTERED_POPUP"
    LOG_DETECTION_EVENT = "LOG_DETECTION_EVENT"


class ActionExecutionState(str, Enum):
    NOT_EVALUATED = "NOT_EVALUATED"
    EXECUTION_DISABLED = "EXECUTION_DISABLED"
    NO_ACTIONS = "NO_ACTIONS"
    PARTIALLY_EXECUTED = "PARTIALLY_EXECUTED"
    EXECUTED = "EXECUTED"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class ActionExecutionInput:
    proposed_actions: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    orchestrator_state: str
    orchestrator_automatic_actions_enabled: bool
    person_id: str | None
    run_id: str
    session_id: str
    timestamp: datetime
    detection_event: DetectionEventActionData | None = None
    popup: PopupActionData | None = None

    def __post_init__(self) -> None:
        if not self.orchestrator_state.strip():
            raise ActionExecutorValidationError("orchestrator_state is required")
        if self.person_id is not None and not self.person_id.strip():
            raise ActionExecutorValidationError("person_id cannot be blank")
        if not self.run_id.strip() or not self.session_id.strip():
            raise ActionExecutorValidationError("run_id and session_id are required")
        if self.timestamp.tzinfo is None:
            raise ActionExecutorValidationError("timestamp must be timezone-aware")


@dataclass(frozen=True, slots=True)
class DetectionEventActionData:
    """Minimum scalar observation payload visible only to the event adapter."""

    recognition_state: str
    display_name_snapshot: str | None = None
    similarity: float | None = None
    quality_score: float | None = None
    camera_id: str | None = None
    face_count: int = 1
    administrative_status: str | None = None

    def __post_init__(self) -> None:
        if not self.recognition_state.strip():
            raise ActionExecutorValidationError("recognition_state is required")
        if self.face_count < 0:
            raise ActionExecutorValidationError("face_count cannot be negative")
        for value in (self.similarity, self.quality_score):
            if value is not None and not math.isfinite(value):
                raise ActionExecutorValidationError("event metric must be finite")


@dataclass(frozen=True, slots=True)
class PopupActionData:
    """PII-free scalar request for the presentation controller."""

    recognition_state: str
    similarity: float | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        if not self.recognition_state.strip():
            raise ActionExecutorValidationError("recognition_state is required")
        if self.similarity is not None and not math.isfinite(self.similarity):
            raise ActionExecutorValidationError("popup similarity must be finite")


@dataclass(frozen=True, slots=True)
class ActionExecutionContext:
    action: ExecutableAction
    person_id: str | None
    run_id: str
    session_id: str
    orchestrator_state: str
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class ActionExecutionResult:
    state: ActionExecutionState
    evaluated: bool
    requested_actions: tuple[str, ...]
    executed_actions: tuple[str, ...]
    skipped_actions: tuple[str, ...]
    failed_actions: tuple[str, ...]
    reasons: tuple[str, ...]
    automatic_execution_enabled: bool
    policy_name: str
    policy_version: str
    timestamp: datetime

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise ActionExecutorValidationError("timestamp must be timezone-aware")
        if not self.policy_name.strip() or not self.policy_version.strip():
            raise ActionExecutorValidationError("policy provenance is required")
        if len(set(self.executed_actions)) != len(self.executed_actions):
            raise ActionExecutorValidationError("executed actions contain duplicates")
