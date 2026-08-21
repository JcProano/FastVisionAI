"""Compatibility facade for attendance schema metadata."""

from .infrastructure.migrations import SCHEMA_VERSION, initialize_schema

__all__ = ["SCHEMA_VERSION", "initialize_schema"]
