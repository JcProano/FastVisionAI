"""Concrete low-risk bridge from ActionExecutor to detection-event history."""

from __future__ import annotations
import logging

from src.core.detection_events import (
    DetectionEventInput, DetectionEventService, DetectionEventType,
)
from src.engine.action_executor import ActionExecutionContext, DetectionEventActionData
from src.core.application_events import ApplicationEventBus, DetectionEventStoredEvent

LOGGER = logging.getLogger(__name__)


class DetectionEventActionAdapterError(RuntimeError):
    """Safe adapter failure without event payload or civil information."""


class DetectionEventServiceActionAdapter:
    __slots__ = ("_service", "_application_events")

    def __init__(
        self, service: DetectionEventService,
        application_event_bus: ApplicationEventBus | None = None,
    ) -> None:
        self._service = service
        self._application_events = application_event_bus

    def log_proposed_event(
        self, context: ActionExecutionContext, event: DetectionEventActionData,
    ) -> None:
        event_type = _event_type(context, event)
        result = self._service.observe(DetectionEventInput(
            event_type=event_type,
            person_id=(context.person_id if event_type is
                       DetectionEventType.REGISTERED_CANDIDATE else None),
            timestamp=context.timestamp,
            camera_id=event.camera_id,
            display_name_snapshot=(event.display_name_snapshot if event_type is
                                   DetectionEventType.REGISTERED_CANDIDATE else None),
            similarity=event.similarity,
            quality_score=event.quality_score,
            recognition_state=event.recognition_state,
            administrative_status=None,
            session_id=context.session_id,
        ))
        if not result.success:
            raise DetectionEventActionAdapterError("detection event service rejected write")
        if self._application_events is not None:
            try:
                self._application_events.publish(DetectionEventStoredEvent(
                    source="detection_event_action_adapter",
                    session_id=context.session_id, run_id=context.run_id,
                    detection_event_id=(None if result.event is None else
                                        result.event.event_id),
                    person_id=(context.person_id if event_type is
                               DetectionEventType.REGISTERED_CANDIDATE else None),
                    detection_event_type=event_type.value, camera_id=event.camera_id,
                    recorded=result.recorded, timestamp=context.timestamp,
                ))
            except Exception as exc:
                LOGGER.error(
                    "Detection application event failed safely; exception_type=%s",
                    type(exc).__name__,
                )


def _event_type(
    context: ActionExecutionContext, event: DetectionEventActionData,
) -> DetectionEventType:
    if event.face_count == 0:
        raise DetectionEventActionAdapterError("no-face observations are not loggable")
    if event.recognition_state == "INCOMPATIBLE":
        return DetectionEventType.INCOMPATIBLE
    if event.face_count > 1:
        return DetectionEventType.MULTIPLE_FACES
    if context.person_id is not None:
        return DetectionEventType.REGISTERED_CANDIDATE
    return DetectionEventType.UNREGISTERED
