"""Compatibility aliases for the People SQLite repository."""

from src.core.people.domain.errors import (
    DuplicateCedulaError,
    DuplicatePersonIdError,
    PersonNotFoundError,
    PersonRepositoryError,
)
from src.core.people.infrastructure import SQLitePeopleRepository

PersonRepository = SQLitePeopleRepository

__all__ = [
    "DuplicateCedulaError",
    "DuplicatePersonIdError",
    "PersonNotFoundError",
    "PersonRepository",
    "PersonRepositoryError",
]
