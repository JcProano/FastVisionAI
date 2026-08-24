"""Use case for updating validated civil person data."""

from ..domain.models import PersonRecord, PersonUpdateRequest
from ..domain.ports import PeopleRepositoryPort


class UpdatePersonUseCase:
    def __init__(self, repository: PeopleRepositoryPort) -> None:
        self._repository = repository

    def execute(self, request: PersonUpdateRequest) -> PersonRecord:
        return self._repository.update(request)
