"""Administratively reset one user's password."""

from ..domain.ports import PasswordHasherPort, UserRepositoryPort
from ._audit import AuditCallback, audit_safely


class ResetUserPasswordUseCase:
    def __init__(
        self,
        repository: UserRepositoryPort,
        hasher: PasswordHasherPort,
        audit_callback: AuditCallback | None = None,
    ) -> None:
        self._repository = repository
        self._hasher = hasher
        self._audit_callback = audit_callback

    def execute(self, user_id: str, new_password: str) -> None:
        self._repository.change_password_hash(
            user_id, self._hasher.hash_password(new_password)
        )
        audit_safely(
            self._audit_callback, "PASSWORD_RESET", {"user_id": user_id}
        )
