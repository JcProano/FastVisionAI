"""Update the safe profile or role of an administrative user."""

from ..domain.models import UserDTO, UserRole, UserUpdateRequest
from ..domain.ports import UserRepositoryPort
from ._audit import AuditCallback, audit_safely


class UpdateUserUseCase:
    def __init__(
        self,
        repository: UserRepositoryPort,
        audit_callback: AuditCallback | None = None,
    ) -> None:
        self._repository = repository
        self._audit_callback = audit_callback

    def execute(
        self,
        user_id: str,
        display_name: str | None = None,
        role: UserRole | str | None = None,
    ) -> UserDTO:
        valid_role = (
            role
            if isinstance(role, UserRole)
            else UserRole(role)
            if role is not None
            else None
        )
        before = self._repository.get_by_user_id(user_id)
        result = self._repository.update_user(
            UserUpdateRequest(user_id, display_name, valid_role)
        )
        event = (
            "USER_ROLE_CHANGED"
            if valid_role is not None
            and before is not None
            and before.role is not result.role
            else "USER_UPDATED"
        )
        audit_safely(self._audit_callback, event, {"user_id": user_id})
        return result
