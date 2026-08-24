"""List safe administrative user projections."""

from ..domain.models import UserDTO
from ..domain.ports import UserRepositoryPort


class ListUsersUseCase:
    def __init__(self, repository: UserRepositoryPort) -> None:
        self._repository = repository

    def execute(self) -> tuple[UserDTO, ...]:
        return self._repository.list_users()
