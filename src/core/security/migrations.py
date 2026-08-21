"""Compatibility exports for security SQLite migrations."""

from .infrastructure.migrations import (
    SCHEMA_VERSION,
    SecurityMigrationError,
    initialize_schema,
)

__all__ = ["SCHEMA_VERSION", "SecurityMigrationError", "initialize_schema"]
