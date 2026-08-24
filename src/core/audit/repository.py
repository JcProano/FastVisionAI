"""Compatibility export for the SQLite audit repository."""

from .infrastructure import SQLiteAuditRepository

AuditRepository = SQLiteAuditRepository

__all__ = ["AuditRepository"]
