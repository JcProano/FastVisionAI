"""Authorized presentation facade for administrative user management."""

from __future__ import annotations

from src.core.security import (
    AuthorizationPermission as Permission,
    ChangeUserStatusUseCase,
    CreateUserUseCase,
    ListUsersUseCase,
    PasswordHasher,
    ResetUserPasswordUseCase,
    UpdateUserUseCase,
    UserRepository,
)

from .contracts import UserSummaryDTO
from .controller import AuthorizationController


class UserManagementController:
    def __init__(
        self,
        repository: UserRepository,
        hasher: PasswordHasher,
        authorization: AuthorizationController,
        audit_callback=None,
    ) -> None:
        self.repository = repository
        self.hasher = hasher
        self.authorization = authorization
        self.audit_callback = audit_callback
        self._list_users = ListUsersUseCase(repository)
        self._create_user = CreateUserUseCase(
            repository, hasher, audit_callback
        )
        self._update_user = UpdateUserUseCase(repository, audit_callback)
        self._change_status = ChangeUserStatusUseCase(
            repository, audit_callback
        )
        self._reset_password = ResetUserPasswordUseCase(
            repository, hasher, audit_callback
        )

    def _require(self) -> None:
        if not self.authorization.can(Permission.MANAGE_USERS):
            raise PermissionError("operation is not authorized")

    def list_users(self) -> tuple[UserSummaryDTO, ...]:
        self._require()
        return tuple(
            UserSummaryDTO(
                user.user_id,
                user.username,
                user.display_name,
                user.role.value,
                user.status.value,
                user.last_login_at.isoformat() if user.last_login_at else None,
            )
            for user in self._list_users.execute()
        )

    def create(self, username, display_name, password, role):
        self._require()
        return self._create_user.execute(
            username, display_name, password, role
        )

    def update(self, user_id, display_name=None, role=None):
        self._require()
        return self._update_user.execute(user_id, display_name, role)

    def set_status(self, user_id, status):
        self._require()
        current = self.authorization.sessions.current()
        return self._change_status.execute(
            user_id,
            status,
            actor_user_id=current.user_id if current else None,
        )

    def reset_password(self, user_id, new_password) -> None:
        self._require()
        self._reset_password.execute(user_id, new_password)
