"""Replace a user's password hash and clear lockout state."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from ..domain.ports import PasswordHasherPort, UserRepositoryPort


class ChangePasswordUseCase:
    def __init__(
        self,
        repository: UserRepositoryPort,
        hasher: PasswordHasherPort,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._hasher = hasher
        self._now = now or (lambda: datetime.now(timezone.utc))

    def execute(self, user_id: str, new_password: str) -> None:
        self._repository.change_password_hash(
            user_id,
            self._hasher.hash_password(new_password),
            now=self._now(),
        )
