"""Create one administrative user with a validated password hash."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from ..domain.models import UserCreateRequest, UserDTO, UserRole
from ..domain.ports import PasswordHasherPort, UserRepositoryPort
from ._audit import AuditCallback, audit_safely


class CreateUserUseCase:
    def __init__(
        self,
        repository: UserRepositoryPort,
        hasher: PasswordHasherPort,
        audit_callback: AuditCallback | None = None,
        *,
        new_id: Callable[[], str] = lambda: str(uuid.uuid4()),
    ) -> None:
        self._repository = repository
        self._hasher = hasher
        self._audit_callback = audit_callback
        self._new_id = new_id

    def execute(
        self,
        username: str,
        display_name: str,
        password: str,
        role: UserRole | str,
    ) -> UserDTO:
        valid_role = role if isinstance(role, UserRole) else UserRole(role)
        result = self._repository.create_user(
            UserCreateRequest(
                self._new_id(), username, display_name, valid_role
            ),
            self._hasher.hash_password(password),
        )
        audit_safely(
            self._audit_callback, "USER_CREATED", {"user_id": result.user_id}
        )
        return result
