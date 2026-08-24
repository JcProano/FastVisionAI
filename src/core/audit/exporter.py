"""Compatibility exports for the CSV audit adapter."""

from .infrastructure.csv_audit_exporter import COLUMNS, CSVAuditExporter

AuditCSVExporter = CSVAuditExporter

__all__ = ["AuditCSVExporter", "COLUMNS"]
