"""PII-resolving read boundary for the independent event database."""
from __future__ import annotations
from datetime import datetime
from pathlib import Path

from src.core.detection_events import (
    DetectionEventDTO, DetectionEventQuery, DetectionEventRepository,
    DetectionEventService, DetectionEventType,
)
from src.core.person_database import PersonRepository
from src.core.security import AuthorizationPermission
from src.ui.identification import IdentityInfoProvider
from .contracts import DetectionHistoryDetailDTO, DetectionHistoryDTO, DetectionHistoryOperationDTO


class DetectionHistoryController:
    def __init__(self, repository: DetectionEventRepository,
                 people: PersonRepository | None = None,
                 service: DetectionEventService | None = None,
                 identity_provider: IdentityInfoProvider | None = None,
                 authorization=None) -> None:
        self.repository = repository; self.people = people; self.service = service
        self.identity_provider = identity_provider; self.authorization = authorization

    def list(self, *, date_from: datetime | None = None, date_to: datetime | None = None,
             person_id: str | None = None, name: str | None = None,
             cedula: str | None = None, camera_id: str | None = None,
             administrative_status: str | None = None,
             event_type: DetectionEventType | None = None,
             limit: int = 100) -> DetectionHistoryDTO:
        self._require_view()
        if cedula and self.people is not None:
            normalized = cedula.strip()
            match = next((item for item in self.people.list(limit=1_000)
                          if item.cedula == normalized), None)
            if match is None: return DetectionHistoryDTO((), 0, "Sin eventos")
            person_id = match.person_id
        if name and self.people is not None:
            normalized = name.casefold().strip()
            matches = tuple(item for item in self.people.list(limit=1_000)
                            if normalized in f"{item.first_name} {item.last_name}".casefold())
            if not matches: return DetectionHistoryDTO((), 0, "Sin eventos")
            if len(matches) > 1:
                return DetectionHistoryDTO((), 0, "La búsqueda civil es ambigua")
            person_id = matches[0].person_id
        records = self.repository.query(DetectionEventQuery(
            date_from, date_to, person_id, event_type, limit, 0,
            camera_id or None, administrative_status or None,
        ))
        events = tuple(self._dto(item) for item in records)
        return DetectionHistoryDTO(events, len(events), f"{len(events)} eventos")

    def recent(self, limit: int = 10) -> tuple[DetectionEventDTO, ...]:
        self._require_view()
        records = self.service.recent(limit) if self.service is not None else ()
        return tuple(self._dto(item) for item in records)

    def recent_identifications(self, limit: int = 5) -> tuple[DetectionEventDTO, ...]:
        self._require_view()
        records = self.service.recent(100) if self.service is not None else ()
        selected = (item for item in records if item.event_type is DetectionEventType.REGISTERED_CANDIDATE)
        return tuple(self._dto(item) for item in tuple(selected)[:limit])

    def detail(self, event_id: str) -> DetectionHistoryDetailDTO | None:
        self._require_view()
        record = self.repository.get_by_event_id(event_id)
        if record is None: return None
        person = None; thumbnail = None
        if record.person_id and self.identity_provider is not None:
            person = self.identity_provider.get_person(record.person_id)
            thumbnail = self.identity_provider.get_thumbnail(record.person_id)
        return DetectionHistoryDetailDTO(self._dto(record), person, thumbnail)

    def export_csv(self, destination: Path, *, limit: int = 500) -> DetectionHistoryOperationDTO:
        self._require_view()
        try:
            count = self.repository.export_csv(destination, DetectionEventQuery(limit=limit))
            return DetectionHistoryOperationDTO(True, "export", "CSV exportado", count)
        except Exception:
            return DetectionHistoryOperationDTO(False, "export", "No se pudo exportar el CSV")

    def _dto(self, item) -> DetectionEventDTO:
        display = item.display_name_snapshot; masked = None; status = item.administrative_status
        if item.person_id and self.people is not None:
            record = self.people.get_by_person_id(item.person_id)
            if record is not None:
                display = f"{record.first_name} {record.last_name}"
                masked = "******" + record.cedula[-4:]
                status = record.status.value
        return DetectionEventDTO(
            item.event_id, item.person_id, item.event_type.value, item.timestamp,
            item.camera_id, display, masked, item.similarity, item.quality_score,
            item.recognition_state, status,
        )

    def _require_view(self) -> None:
        if (self.authorization is not None and not
                self.authorization.can(AuthorizationPermission.VIEW_DETECTION_HISTORY)):
            raise PermissionError("No tiene permiso para consultar el historial")
