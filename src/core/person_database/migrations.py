"""Compatibility exports for the People SQLite schema."""

from src.core.people.infrastructure.migrations import (
    SCHEMA_VERSION,
    PersonDatabaseMigrationError,
    initialize_schema,
)

__all__ = ["PersonDatabaseMigrationError", "SCHEMA_VERSION", "initialize_schema"]
