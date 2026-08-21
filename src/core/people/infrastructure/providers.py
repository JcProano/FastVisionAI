"""Local-only provider abstraction; no external identity service is implemented."""

from __future__ import annotations

from ..domain.models import PersonRecord, PersonSearchQuery
from ..domain.ports import IdentityDataProvider
from .sqlite_repository import SQLitePeopleRepository


class SQLiteIdentityDataProvider:
    def __init__(self, repository: SQLitePeopleRepository) -> None:
        self._repository = repository

    def get_by_person_id(self, person_id: str) -> PersonRecord | None:
        return self._repository.get_by_person_id(person_id)

    def get_by_cedula(self, cedula: str) -> PersonRecord | None:
        return self._repository.get_by_cedula(cedula)

    def search(self, query: PersonSearchQuery) -> tuple[PersonRecord, ...]:
        return self._repository.search(query)
