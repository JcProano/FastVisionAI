"""Safe report exporters; optional formats never break module imports."""
from __future__ import annotations
import csv
import importlib.util
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from pathlib import Path

from .contracts import (
    DateRangeReportDTO, ReportExportError, ReportExportResultDTO,
    ReportExportUnavailableError, ReportFormat,
)


class ReportExporter:
    @staticmethod
    def excel_available() -> bool:
        return importlib.util.find_spec("openpyxl") is not None

    def export_csv(self, report, destination: Path, *, overwrite: bool = False):
        if destination.exists() and not overwrite:
            raise ReportExportError("export destination already exists")
        headers, rows = _table(report)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with destination.open("w" if overwrite else "x", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream); writer.writerow(headers)
                writer.writerows(tuple(_safe(value) for value in row) for row in rows)
        except ReportExportError: raise
        except Exception as exc: raise ReportExportError("CSV export failed") from exc
        return ReportExportResultDTO(True, ReportFormat.CSV, destination.name,
                                     f"{len(rows)} filas exportadas", False)

    def export_excel(self, report, destination: Path, *, overwrite: bool = False):
        if not self.excel_available():
            raise ReportExportUnavailableError("Excel export is unavailable")
        raise ReportExportUnavailableError("Excel export is not enabled in this phase")

    def export_pdf(self, report, destination: Path, *, overwrite: bool = False):
        raise ReportExportUnavailableError("PDF export is unavailable")


def _table(report):
    values = report.days if isinstance(report, DateRangeReportDTO) else (report,)
    if not values or not is_dataclass(values[0]):
        raise ReportExportError("report type is not exportable")
    records = [asdict(value) for value in values]
    headers = tuple(records[0])
    rows = tuple(tuple(record[key] for key in headers) for record in records)
    return headers, rows


def _safe(value):
    if isinstance(value, (datetime, date)): return value.isoformat()
    if value is None: return ""
    if isinstance(value, (tuple, list, dict)): return str(value)
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return "'" + value
    return value
