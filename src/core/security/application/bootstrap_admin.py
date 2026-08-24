"""Create the first local administrator through explicit dependencies."""

from ..domain.models import (
    AuthenticationResult,
    UserCreateRequest,
)
from ..domain.ports import PasswordHasherPort, UserRepositoryPort


class BootstrapAdminUseCase:
    def __init__(
        self, repository: UserRepositoryPort, hasher: PasswordHasherPort
    ) -> None:
        self._repository = repository
        self._hasher = hasher

    def execute(
        self, request: UserCreateRequest, password: str
    ) -> AuthenticationResult:
        hashed = self._hasher.hash_password(password)
        user = self._repository.bootstrap_admin(request, hashed)
        return AuthenticationResult(True, "Administrador inicial creado.", user)
