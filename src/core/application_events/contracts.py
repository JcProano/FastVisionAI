"""Immutable, payload-minimal application event contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING
from uuid import uuid4

if TYPE_CHECKING:
    from src.ui.contracts import (
        ActionExecutorDTO, DecisionOrchestratorDTO, IdentificationPolicyDTO,
        MonitoringDTO, StabilityDTO,
    )


class ApplicationEventValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class ApplicationEvent:
    source: str
    session_id: str | None = None
    run_id: str | None = None
    event_id: str = field(default_factory=lambda: str(uuid4()))
    event_type: str = field(default="application.event", init=False)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        for name, value in (
            ("event_id", self.event_id), ("event_type", self.event_type),
            ("source", self.source),
        ):
            if not value.strip():
                raise ApplicationEventValidationError(f"{name} is required")
        for name, value in (("session_id", self.session_id), ("run_id", self.run_id)):
            if value is not None and not value.strip():
                raise ApplicationEventValidationError(f"{name} cannot be blank")
        if self.timestamp.tzinfo is None:
            raise ApplicationEventValidationError("timestamp must be timezone-aware")


@dataclass(frozen=True, slots=True, kw_only=True)
class MonitoringUpdatedEvent(ApplicationEvent):
    monitoring: MonitoringDTO
    event_type: str = field(default="monitoring.updated", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class StabilityUpdatedEvent(ApplicationEvent):
    stability: StabilityDTO
    event_type: str = field(default="stability.updated", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class IdentificationPolicyUpdatedEvent(ApplicationEvent):
    policy: IdentificationPolicyDTO
    event_type: str = field(default="identification_policy.updated", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class DecisionUpdatedEvent(ApplicationEvent):
    decision: DecisionOrchestratorDTO
    event_type: str = field(default="decision.updated", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class ActionExecutionUpdatedEvent(ApplicationEvent):
    execution: ActionExecutorDTO
    event_type: str = field(default="action_execution.updated", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class EnrollmentStartedEvent(ApplicationEvent):
    person_id: str | None
    state: str
    message: str
    event_type: str = field(default="enrollment.started", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class EnrollmentFinishedEvent(ApplicationEvent):
    person_id: str | None
    state: str
    message: str
    event_type: str = field(default="enrollment.finished", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class EnrollmentCancelledEvent(ApplicationEvent):
    person_id: str | None
    state: str
    message: str
    event_type: str = field(default="enrollment.cancelled", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class DetectionEventStoredEvent(ApplicationEvent):
    detection_event_id: str | None
    person_id: str | None
    detection_event_type: str
    camera_id: str | None
    recorded: bool
    event_type: str = field(default="detection_event.processed", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class PopupRequestedEvent(ApplicationEvent):
    popup_action: str
    person_id: str | None
    presentation_state: str
    reason: str | None
    event_type: str = field(default="popup.requested", init=False)


@dataclass(frozen=True, slots=True, kw_only=True)
class PopupDismissedEvent(ApplicationEvent):
    popup_type: str
    reason: str
    event_type: str = field(default="popup.dismissed", init=False)

