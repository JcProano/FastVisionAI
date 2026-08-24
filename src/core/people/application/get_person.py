"""Use case for finding one person by its internal identifier."""

from ..domain.models import PersonRecord
from ..domain.ports import PeopleRepositoryPort


class GetPersonUseCase:
    def __init__(self, repository: PeopleRepositoryPort) -> None:
        self._repository = repository

    def execute(self, person_id: str) -> PersonRecord | None:
        return self._repository.get_by_person_id(person_id)
