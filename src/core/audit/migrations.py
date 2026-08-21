"""Compatibility exports for audit SQLite migrations."""

from .infrastructure.migrations import SCHEMA_VERSION, initialize_schema

__all__ = ["SCHEMA_VERSION", "initialize_schema"]
