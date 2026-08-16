"""Fail-safe consumer from persisted recognition events to automatic attendance."""
from __future__ import annotations
import logging

from src.core.application_events import (
    ApplicationEventBus, AttendanceRecordedEvent, DetectionEventStoredEvent,
)
from src.core.attendance import AttendanceService
from src.core.detection_events import DetectionEventType
from src.camera.source_discovery import redact_url

LOGGER = logging.getLogger(__name__)


class AutomaticAttendanceEventAdapter:
    def __init__(self, service: AttendanceService, bus: ApplicationEventBus) -> None:
        self.service = service; self.bus = bus

    def __call__(self, event: DetectionEventStoredEvent) -> None:
        if (not event.recorded or event.detection_event_id is None
                or event.person_id is None
                or event.detection_event_type != DetectionEventType.REGISTERED_CANDIDATE.value):
            return
        result = self.service.consume_detection_event(
            event.person_id, source_event_id=event.detection_event_id,
            camera_id=(_safe_camera(event.camera_id)), timestamp=event.timestamp,
        )
        if result.reason == "persistence_error":
            LOGGER.warning("Automatic attendance persistence failed safely")
        if not result.eligible or result.record is None:
            return
        record = result.record
        self.bus.publish(AttendanceRecordedEvent(
            source="automatic_attendance", session_id=event.session_id,
            run_id=event.run_id, attendance_id=record.attendance_id,
            person_id=record.person_id, attendance_event_type=record.event_type.value,
            camera_id=record.camera_id, source_event_id=event.detection_event_id,
            timestamp=record.timestamp,
        ))


def _safe_camera(value: str | None) -> str | None:
    if value is None:return None
    cleaned=" ".join(value.split())[:160]
    return redact_url(cleaned) if "://" in cleaned else cleaned
