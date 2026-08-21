"""Authenticate one user without leaking account existence or lock state."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone

from ..domain.models import (
    AuthenticationPolicy,
    AuthenticationRequest,
    AuthenticationResult,
    PasswordHashDTO,
    UserStatus,
)
from ..domain.ports import PasswordHasherPort, UserRepositoryPort


class AuthenticateUserUseCase:
    INVALID = "Credenciales inválidas."
    UNAVAILABLE = "Inicio de sesión temporalmente no disponible."

    def __init__(
        self,
        repository: UserRepositoryPort,
        hasher: PasswordHasherPort,
        policy: AuthenticationPolicy | None = None,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._hasher = hasher
        self._policy = policy or AuthenticationPolicy()
        self._now = now or (lambda: datetime.now(timezone.utc))
        self._dummy = hasher.hash_password("FastVision0DummyPassword")

    def execute(self, request: AuthenticationRequest) -> AuthenticationResult:
        now = self._now()
        record = self._repository.get_by_username(request.username)
        if record is None or record.status is UserStatus.DISABLED:
            self._hasher.verify_password(request.password, self._dummy)
            return AuthenticationResult(False, self.INVALID)
        if record.locked_until and record.locked_until > now:
            self._hasher.verify_password(request.password, self._dummy)
            return AuthenticationResult(
                False, self.UNAVAILABLE, temporarily_unavailable=True
            )
        stored = PasswordHashDTO(
            record.password_hash,
            record.password_salt,
            record.password_algorithm,
            record.password_parameters,
        )
        if not self._hasher.verify_password(request.password, stored):
            attempts = record.failed_attempts + 1
            locked_until = (
                now + timedelta(seconds=self._policy.lockout_seconds)
                if attempts >= self._policy.max_failed_attempts
                else None
            )
            self._repository.update_login_failure(
                record.user_id,
                failed_attempts=attempts,
                locked_until=locked_until,
                now=now,
            )
            return AuthenticationResult(
                False,
                self.UNAVAILABLE if locked_until else self.INVALID,
                temporarily_unavailable=locked_until is not None,
            )
        user = self._repository.update_login_success(record.user_id, now=now)
        return AuthenticationResult(True, "Inicio de sesión correcto.", user)
