"""Read-only consolidation over existing dashboard-facing controllers."""
from __future__ import annotations
from dataclasses import replace
from datetime import timedelta
from zoneinfo import ZoneInfo

from src.core.detection_events import DetectionEventType
from src.core.security import AuthorizationPermission
from src.core.time_provider import Clock
from .professional_contracts import (
    DashboardLiveStateDTO, DashboardPhotoDTO, DashboardSnapshotDTO,
    RecentAttendanceRowDTO, RecentRecognitionRowDTO,
)


class ProfessionalDashboardController:
    def __init__(self, detection_history, attendance, reports, identity_provider,
                 authorization=None, system_health=None, *, clock: Clock | None = None,
                 timezone_name: str = "America/Guayaquil") -> None:
        self.detection_history=detection_history;self.attendance=attendance
        self.reports=reports;self.identity_provider=identity_provider
        self.authorization=authorization;self.clock=clock or Clock()
        self.system_health=system_health
        self.timezone_name=timezone_name;self.timezone=ZoneInfo(timezone_name)

    def snapshot(self, live: DashboardLiveStateDTO, *, refresh_statistics: bool,
                 previous: DashboardSnapshotDTO | None = None) -> DashboardSnapshotDTO:
        self._require(AuthorizationPermission.VIEW_DASHBOARD)
        today=self.clock.local_today(self.timezone_name)
        start,end=self.clock.local_day_utc_bounds(today,self.timezone_name)
        recognitions=();attendance_rows=()
        if self._can(AuthorizationPermission.VIEW_DETECTION_HISTORY):
            recognitions=self.detection_history.list(
                date_from=start,date_to=end-timedelta(microseconds=1),
                event_type=DetectionEventType.REGISTERED_CANDIDATE,limit=5,
            ).events
        if self._can(AuthorizationPermission.VIEW_ATTENDANCE):
            attendance_rows=self.attendance.day_list(day=today).days[:5]
        if refresh_statistics or previous is None:
            report=self.reports.service.daily_report(today)
            attendance_summary=(self.attendance.attendance_today()
                                if self._can(AuthorizationPermission.VIEW_ATTENDANCE) else None)
            people_present=None if attendance_summary is None else attendance_summary.present
            late=None if attendance_summary is None else attendance_summary.late
            recognized=(report.registered_candidate_events
                        if self._can(AuthorizationPermission.VIEW_DETECTION_HISTORY) else None)
            check_ins=(report.attendance_check_ins
                       if self._can(AuthorizationPermission.VIEW_ATTENDANCE) else None)
        else:
            people_present=previous.people_present;recognized=previous.recognitions_today
            check_ins=previous.check_ins_today;late=previous.late_today
        database_state="OK"
        if self.system_health is not None:
            health=self.system_health.snapshot()
            databases=tuple(item for item in health.components if "database" in item.component)
            if any(item.level.value not in {"OK","DISABLED"} for item in databases):
                database_state="Degradada"
        return DashboardSnapshotDTO(
            people_present,recognized,check_ins,late,
            tuple(self._recognition(item) for item in recognitions[:5]),
            tuple(self._attendance(item) for item in attendance_rows[:5]),
            _camera_state(live.camera_state),database_state,max(0,live.gallery_identities),
            _recognition_state(live.runtime_state,live.recognition_state),
            "Activa" if self.attendance is not None and
                self.attendance.service.policy.automatic_attendance_enabled else "Desactivada",
            self.clock.utc_now(),
        )

    def degraded(self, previous: DashboardSnapshotDTO) -> DashboardSnapshotDTO:
        return replace(previous,database_state="Degradada",generated_at=self.clock.utc_now())

    def _recognition(self,item) -> RecentRecognitionRowDTO:
        return RecentRecognitionRowDTO(self._photo(item.person_id),item.display_name or "Persona registrada",
            item.timestamp.astimezone(self.timezone).strftime("%H:%M:%S"),item.similarity)

    def _attendance(self,item) -> RecentAttendanceRowDTO:
        return RecentAttendanceRowDTO(self._photo(item.person_id),item.display_name or "Persona registrada",
            _time(item.check_in,self.timezone),_time(item.check_out,self.timezone),item.status)

    def _photo(self,person_id: str | None) -> DashboardPhotoDTO:
        if person_id is None:return DashboardPhotoDTO(False)
        value=self.identity_provider.get_thumbnail(person_id)
        return DashboardPhotoDTO(value.available,value.width,value.height,value.format,value.image_bytes)

    def _can(self, permission: AuthorizationPermission) -> bool:
        return self.authorization is None or self.authorization.can(permission)

    def _require(self, permission: AuthorizationPermission) -> None:
        if not self._can(permission):raise PermissionError("operation is not authorized")


def _time(value,zone):return None if value is None else value.astimezone(zone).strftime("%H:%M:%S")


def _camera_state(value: str) -> str:
    normalized=value.upper()
    if "RECONNECT" in normalized:return "Reconectando"
    if normalized in {"CONNECTED","RUNNING","OPEN"}:return "Conectada"
    if normalized in {"ERROR","FAILED"}:return "Error"
    return "Desconectada"


def _recognition_state(runtime: str, recognition: str) -> str:
    if "PAUS" in recognition.upper():return "Pausado"
    if runtime.upper() in {"RUNNING","ACTIVE"}:return "Activo"
    return "Detenido"
