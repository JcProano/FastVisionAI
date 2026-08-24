"""Use case enforcing valid administrative status transitions."""

from ..domain.errors import PersonNotFoundError, PersonStatusTransitionError
from ..domain.models import PersonRecord, PersonStatus
from ..domain.ports import PeopleRepositoryPort


class ChangePersonStatusUseCase:
    _ALLOWED_TRANSITIONS = {
        (PersonStatus.ACTIVE, PersonStatus.DISABLED),
        (PersonStatus.DISABLED, PersonStatus.ACTIVE),
    }

    def __init__(self, repository: PeopleRepositoryPort) -> None:
        self._repository = repository

    def execute(self, person_id: str, target: PersonStatus) -> PersonRecord:
        current = self._repository.get_by_person_id(person_id)
        if current is None:
            raise PersonNotFoundError("person does not exist")
        if (current.status, target) not in self._ALLOWED_TRANSITIONS:
            raise PersonStatusTransitionError(
                f"transition from {current.status.value} to {target.value} is not allowed"
            )
        return self._repository.set_status(person_id, target)
