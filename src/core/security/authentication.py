"""Compatibility facade for explicit authentication use cases."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from .application import (
    AuthenticateUserUseCase,
    BootstrapAdminUseCase,
    ChangePasswordUseCase,
)
from .domain.models import (
    AuthenticationPolicy,
    AuthenticationRequest,
    AuthenticationResult,
    UserCreateRequest,
)
from .domain.ports import PasswordHasherPort, UserRepositoryPort


class AuthenticationService:
    INVALID = AuthenticateUserUseCase.INVALID
    UNAVAILABLE = AuthenticateUserUseCase.UNAVAILABLE

    def __init__(
        self,
        repository: UserRepositoryPort,
        hasher: PasswordHasherPort,
        policy: AuthenticationPolicy | None = None,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.repository = repository
        self.hasher = hasher
        self.policy = policy or AuthenticationPolicy()
        self._authenticate = AuthenticateUserUseCase(
            repository, hasher, self.policy, now=now
        )
        self._bootstrap = BootstrapAdminUseCase(repository, hasher)
        self._change_password = ChangePasswordUseCase(
            repository, hasher, now=now
        )

    def bootstrap_admin(
        self, request: UserCreateRequest, password: str
    ) -> AuthenticationResult:
        return self._bootstrap.execute(request, password)

    def authenticate(
        self, request: AuthenticationRequest
    ) -> AuthenticationResult:
        return self._authenticate.execute(request)

    def change_password(self, user_id: str, new_password: str) -> None:
        self._change_password.execute(user_id, new_password)


__all__ = ["AuthenticationPolicy", "AuthenticationService"]
