"""UI projection over the attendance and civil repositories."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from pathlib import Path
from src.core.time_provider import Clock

from src.core.attendance import (
    AttendanceDTO, AttendanceEventType, AttendancePolicy, AttendanceQuery,
    AttendanceRepository, AttendanceService, project_days, today_summary,
)
from src.core.person_database import PersonRepository

from .contracts import (AttendanceDashboardDTO, AttendanceDayDTO, AttendanceDayListDTO, AttendanceDetailDTO,
                        AttendanceListDTO, AttendanceUIResult, PersonAttendanceSummaryDTO)


class AttendanceUIController:
    def __init__(
        self, service: AttendanceService, repository: AttendanceRepository,
        people: PersonRepository, authorization=None, audit_callback=None,
        clock: Clock | None = None, presentation_timezone: str = "America/Guayaquil",
    ) -> None:
        self.service = service
        self.repository = repository
        self.people = people
        self.authorization = authorization
        self.audit_callback = audit_callback
        self.clock=clock or Clock();self.presentation_timezone=presentation_timezone
        self.identity_provider = None

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
        selected=day or self.clock.local_today(self.presentation_timezone);start,end=self.clock.local_day_utc_bounds(selected,self.presentation_timezone);return self.repository.summary_between(selected,start,end)

    def day_list(self, *, day: date | None = None, name: str | None = None,
                 cedula: str | None = None, status: str | None = None) -> AttendanceDayListDTO:
        self._require("VIEW_ATTENDANCE")
        selected = day or self.clock.local_today(self.presentation_timezone)
        start,end=self.clock.local_day_utc_bounds(selected,self.presentation_timezone)
        from datetime import timedelta
        rows=self.repository.query(AttendanceQuery(date_from=start,date_to=end-timedelta(microseconds=1),limit=500))
        values=[]
        for item in project_days(rows,self.service.policy,today=self.clock.local_today(self.presentation_timezone)):
            person=self.people.get_by_person_id(item.person_id)
            display=None if person is None else f"{person.first_name} {person.last_name}"
            masked=None if person is None else "******"+person.cedula[-4:]
            if name and (display is None or name.casefold().strip() not in display.casefold()):continue
            if cedula and (person is None or person.cedula != cedula.strip()):continue
            if status and item.status.value != status:continue
            values.append(AttendanceDayDTO(item.person_id,item.local_date,display,masked,
                item.check_in_utc,item.check_out_utc,item.worked_seconds,item.late_seconds,
                item.overtime_seconds,item.status.value,item.check_in_source,item.check_out_source,
                item.check_in_camera,item.check_out_camera))
        return AttendanceDayListDTO(tuple(values),len(values),f"{len(values)} jornadas")

    def attendance_today(self):
        self._require("VIEW_ATTENDANCE")
        selected=self.clock.local_today(self.presentation_timezone)
        start,end=self.clock.local_day_utc_bounds(selected,self.presentation_timezone)
        from datetime import timedelta
        rows=self.repository.query(AttendanceQuery(date_from=start,date_to=end-timedelta(microseconds=1),limit=500))
        days=project_days(rows,self.service.policy,today=selected)
        summary=today_summary(days,rows,selected)
        latest=[]
        for row in rows[:5]:
            person=self.people.get_by_person_id(row.person_id)
            name="Persona" if person is None else f"{person.first_name} {person.last_name}"
            latest.append((name,row.event_type.value,row.timestamp))
        return AttendanceDashboardDTO(summary.present,summary.completed,summary.pending,
                                      summary.late,tuple(latest))

    def detail(self, person_id: str, day: date) -> AttendanceDetailDTO | None:
        self._require("VIEW_ATTENDANCE")
        selected=next((item for item in self.day_list(day=day).days
                       if item.person_id==person_id),None)
        if selected is None:return None
        person=thumbnail=None
        if self.identity_provider is not None:
            person=self.identity_provider.get_person(person_id)
            thumbnail=self.identity_provider.get_thumbnail(person_id)
        return AttendanceDetailDTO(selected,person,thumbnail)

    def person_summary(
        self, person_id: str, day: date | None = None,
    ) -> PersonAttendanceSummaryDTO:
        check_ins = {AttendanceEventType.CHECK_IN, AttendanceEventType.MANUAL_CHECK_IN}
        check_outs = {AttendanceEventType.CHECK_OUT, AttendanceEventType.MANUAL_CHECK_OUT}
        today = day or self.clock.local_today(self.presentation_timezone)
        latest_by_type = tuple(
            rows[0] for event_type in AttendanceEventType
            if (rows := self.repository.query(AttendanceQuery(
                person_id=person_id, event_type=event_type, limit=1,
            )))
        )
        start,end=self.clock.local_day_utc_bounds(today,self.presentation_timezone)
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
