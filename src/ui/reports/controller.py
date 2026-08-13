"""Safe UI controller for read-only local reports."""
from __future__ import annotations
from datetime import date, timedelta
from pathlib import Path
from src.core.time_provider import Clock

from src.core.reports import ReportExporter, ReportValidationError


class ReportController:
    REPORT_TYPES = (
        "Resumen diario", "Rango de fechas", "Por persona",
        "Resumen de detecciones", "Resumen del sistema",
    )

    def __init__(self, service, exporter: ReportExporter | None = None, authorization=None, audit_callback=None, clock:Clock|None=None) -> None:
        self.service = service; self.exporter = exporter or ReportExporter()
        self.authorization = authorization
        self.last_report = None
        self.audit_callback = audit_callback
        self.last_report_type = None
        self.clock=clock or Clock()

    def generate(
        self, report_type: str, date_from: str, date_to: str,
        person_id: str | None = None,
    ):
        self._require("VIEW_REPORTS")
        try:
            start = date.fromisoformat(date_from)
            end = date.fromisoformat(date_to)
        except ValueError as exc:
            raise ReportValidationError("dates must use YYYY-MM-DD") from exc
        if report_type == "Resumen diario": result = self.service.daily_report(start)
        elif report_type == "Rango de fechas": result = self.service.date_range_report(start, end)
        elif report_type == "Por persona":
            if not person_id or not person_id.strip():
                raise ReportValidationError("person_id is required")
            result = self.service.person_report(person_id.strip(), start, end)
        elif report_type == "Resumen de detecciones":
            result = self.service.detection_summary(start, end)
        elif report_type == "Resumen del sistema": result = self.service.system_summary(start)
        else: raise ReportValidationError("report type is invalid")
        self.last_report = result
        self.last_report_type = report_type
        return result

    def default_dates(self, today: date | None = None) -> tuple[str, str]:
        end = today or self.clock.local_today(self.service.policy.presentation_timezone)
        start = end - timedelta(days=self.service.policy.default_range_days - 1)
        return start.isoformat(), end.isoformat()

    def export_csv(self, destination: Path, *, overwrite: bool = False):
        self._require("EXPORT_REPORTS")
        if self.last_report is None: raise ReportValidationError("generate a report first")
        result=self.exporter.export_csv(self.last_report, destination, overwrite=overwrite)
        if self.audit_callback:
            try:self.audit_callback("REPORT_EXPORTED",{"report_type":self.last_report_type or "unknown","format":"CSV"})
            except Exception:pass
        return result

    @property
    def excel_available(self) -> bool: return self.exporter.excel_available()

    def _require(self, permission: str) -> None:
        if self.authorization is not None:
            from src.core.security import AuthorizationPermission
            if not self.authorization.can(AuthorizationPermission(permission)):
                raise PermissionError("operation is not authorized")
