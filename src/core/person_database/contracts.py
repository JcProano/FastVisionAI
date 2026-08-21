"""Compatibility exports for People domain models."""

from src.core.people.domain.models import (
    PersonCreateRequest,
    PersonDatabaseStats,
    PersonRecord,
    PersonSearchQuery,
    PersonStatus,
    PersonUpdateRequest,
)

__all__ = [name for name in globals() if name.startswith("Person")]
