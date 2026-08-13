"""UI projection over the attendance and civil repositories."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from pathlib import Path

from src.core.attendance import (
    AttendanceDTO, AttendanceEventType, AttendancePolicy, AttendanceQuery,
    AttendanceRepository, AttendanceService,
)
from src.core.person_database import PersonRepository

from .contracts import AttendanceListDTO, AttendanceUIResult, PersonAttendanceSummaryDTO


class AttendanceUIController:
    def __init__(
        self, service: AttendanceService, repository: AttendanceRepository,
        people: PersonRepository, authorization=None, audit_callback=None,
    ) -> None:
        self.service = service
        self.repository = repository
        self.people = people
        self.authorization = authorization
        self.audit_callback = audit_callback

    def manual_check_in(self, person_id: str, **kwargs: object) -> AttendanceUIResult:
        self._require("MANUAL_ATTENDANCE")
        result=self._result(self.service.manual_check_in(person_id, **kwargs))
        if result.success:self._audit("MANUAL_CHECK_IN",{"person_id":person_id,"entity_id":result.attendance_id or ""})
        return result

    def manual_check_out(self, person_id: str, **kwargs: object) -> AttendanceUIResult:
        self._require("MANUAL_ATTENDANCE")
        result=self._result(self.service.manual_check_out(person_id, **kwargs))
        if result.success:self._audit("MANUAL_CHECK_OUT",{"person_id":person_id,"entity_id":result.attendance_id or ""})
        return result

    def list(
        self, *, date_from: datetime | None = None, date_to: datetime | None = None,
        person_id: str | None = None, name: str | None = None,
        event_type: AttendanceEventType | None = None, limit: int = 100,
    ) -> AttendanceListDTO:
        self._require("VIEW_ATTENDANCE")
        if name:
            needle = name.casefold()
            matches = [
                person for person in self.people.list(limit=1_000)
                if needle in f"{person.first_name} {person.last_name}".casefold()
            ]
            if len(matches) != 1:
                return AttendanceListDTO((), 0, "Sin coincidencia única")
            person_id = matches[0].person_id
        rows = self.repository.query(AttendanceQuery(
            date_from, date_to, person_id, event_type, limit,
        ))
        events = tuple(self._dto(item) for item in rows)
        return AttendanceListDTO(events, len(events), f"{len(events)} marcaciones")

    def daily_summary(self, day: date | None = None):
        return self.repository.daily_summary(day or date.today())

    def person_summary(
        self, person_id: str, day: date | None = None,
    ) -> PersonAttendanceSummaryDTO:
        check_ins = {AttendanceEventType.CHECK_IN, AttendanceEventType.MANUAL_CHECK_IN}
        check_outs = {AttendanceEventType.CHECK_OUT, AttendanceEventType.MANUAL_CHECK_OUT}
        today = day or date.today()
        latest_by_type = tuple(
            rows[0] for event_type in AttendanceEventType
            if (rows := self.repository.query(AttendanceQuery(
                person_id=person_id, event_type=event_type, limit=1,
            )))
        )
        start = datetime.combine(today, time.min, tzinfo=timezone.utc)
        end = datetime.combine(today, time.max, tzinfo=timezone.utc)
        return PersonAttendanceSummaryDTO(
            max((item.timestamp for item in latest_by_type if item.event_type in check_ins),
                default=None),
            max((item.timestamp for item in latest_by_type if item.event_type in check_outs),
                default=None),
            self.repository.count_for_person_between(person_id, start, end),
        )

    def export_csv(self, path: Path, limit: int = 500) -> AttendanceUIResult:
        self._require("VIEW_ATTENDANCE")
        try:
            count = self.repository.export_csv(path, AttendanceQuery(limit=limit))
            return AttendanceUIResult(True, f"{count} eventos exportados")
        except Exception:
            return AttendanceUIResult(False, "No se pudo exportar asistencia")

    def _dto(self, record) -> AttendanceDTO:
        person = self.people.get_by_person_id(record.person_id)
        display_name = f"{person.first_name} {person.last_name}" if person else None
        masked_cedula = "******" + person.cedula[-4:] if person else None
        return AttendanceDTO(
            record.attendance_id, record.person_id, display_name, masked_cedula,
            record.event_type.value, record.timestamp, record.camera_id,
            record.source_event_id, record.notes,
        )

    @staticmethod
    def _result(result) -> AttendanceUIResult:
        return AttendanceUIResult(
            result.success,
            "Marcación registrada" if result.success else result.reason,
            result.record.attendance_id if result.record else None,
        )

    def _require(self, permission: str) -> None:
        if self.authorization is not None:
            from src.core.security import AuthorizationPermission
            if not self.authorization.can(AuthorizationPermission(permission)):
                raise PermissionError("operation is not authorized")

    def _audit(self,event,payload):
        if self.audit_callback:
            try:self.audit_callback(event,payload)
            except Exception:pass
