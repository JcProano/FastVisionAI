"""Use case for searching civil person records."""

from ..domain.models import PersonRecord, PersonSearchQuery
from ..domain.ports import PeopleRepositoryPort


class SearchPeopleUseCase:
    def __init__(self, repository: PeopleRepositoryPort) -> None:
        self._repository = repository

    def execute(self, query: PersonSearchQuery) -> tuple[PersonRecord, ...]:
        return self._repository.search(query)
