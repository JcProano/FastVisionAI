"""Compatibility exports for People enrollment domain contracts."""

from src.core.people.domain import (
    ExistingActivePersonError,
    ExistingDisabledPersonError,
    ExistingPendingPersonError,
    PersonEnrollmentCoordinationError,
    PersonEnrollmentState,
)

__all__ = [name for name in globals() if not name.startswith("_")]
