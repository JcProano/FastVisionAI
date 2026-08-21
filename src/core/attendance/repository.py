"""Compatibility facade for the former concrete repository name."""

from .infrastructure.sqlite_repository import SQLiteAttendanceRepository

AttendanceRepository = SQLiteAttendanceRepository

__all__ = ["AttendanceRepository", "SQLiteAttendanceRepository"]
