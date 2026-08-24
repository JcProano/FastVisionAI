"""Change user status while preventing an authenticated self-disable."""

from ..domain.models import UserDTO, UserStatus
from ..domain.ports import UserRepositoryPort
from ._audit import AuditCallback, audit_safely


class ChangeUserStatusUseCase:
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
        status: UserStatus | str,
        *,
        actor_user_id: str | None = None,
    ) -> UserDTO:
        target = status if isinstance(status, UserStatus) else UserStatus(status)
        if actor_user_id == user_id and target is UserStatus.DISABLED:
            raise PermissionError("self-disable is not allowed")
        result = self._repository.set_status(user_id, target)
        event = (
            "USER_DISABLED"
            if target is UserStatus.DISABLED
            else "USER_ENABLED"
        )
        audit_safely(self._audit_callback, event, {"user_id": user_id})
        return result
