"""Compatibility exports for audit sanitization policy."""

from .domain.sanitization import sanitize_message, sanitize_metadata

__all__ = ["sanitize_message", "sanitize_metadata"]
