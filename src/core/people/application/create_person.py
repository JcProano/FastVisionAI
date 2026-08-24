"""Use case for creating a pending civil person record."""

from ..domain.models import PersonCreateRequest, PersonRecord
from ..domain.ports import PeopleRepositoryPort


class CreatePersonUseCase:
    def __init__(self, repository: PeopleRepositoryPort) -> None:
        self._repository = repository

    def execute(self, request: PersonCreateRequest) -> PersonRecord:
        return self._repository.create(request)
