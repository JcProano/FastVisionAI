"""Concrete low-risk bridge from ActionExecutor to detection-event history."""

from __future__ import annotations

from src.core.detection_events import (
    DetectionEventInput, DetectionEventService, DetectionEventType,
)
from src.engine.action_executor import ActionExecutionContext, DetectionEventActionData


class DetectionEventActionAdapterError(RuntimeError):
    """Safe adapter failure without event payload or civil information."""


class DetectionEventServiceActionAdapter:
    __slots__ = ("_service",)

    def __init__(self, service: DetectionEventService) -> None:
        self._service = service

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

