"""Local password authentication without biometric coupling."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .contracts import AuthenticationRequest, AuthenticationResult, PasswordHashDTO, UserCreateRequest, UserStatus
from .passwords import PasswordHasher
from .repository import UserRepository


@dataclass(frozen=True, slots=True)
class AuthenticationPolicy:
    max_failed_attempts: int = 5
    lockout_seconds: int = 300
    def __post_init__(self):
        if self.max_failed_attempts < 1 or self.lockout_seconds < 1:
            raise ValueError("authentication policy is invalid")


class AuthenticationService:
    INVALID = "Credenciales inválidas."
    UNAVAILABLE = "Inicio de sesión temporalmente no disponible."

    def __init__(self, repository: UserRepository, hasher: PasswordHasher, policy: AuthenticationPolicy | None = None, *, now=None) -> None:
        self.repository = repository; self.hasher = hasher
        self.policy = policy or AuthenticationPolicy(); self._now = now or (lambda: datetime.now(timezone.utc))
        self._dummy = hasher.hash_password("FastVision0DummyPassword")

    def bootstrap_admin(self, request: UserCreateRequest, password: str) -> AuthenticationResult:
        hashed = self.hasher.hash_password(password)
        user = self.repository.bootstrap_admin(request, hashed)
        return AuthenticationResult(True, "Administrador inicial creado.", user)

    def authenticate(self, request: AuthenticationRequest) -> AuthenticationResult:
        now = self._now()
        record = self.repository.get_by_username(request.username)
        if record is None:
            self.hasher.verify_password(request.password, self._dummy)
            return AuthenticationResult(False, self.INVALID)
        if record.status is UserStatus.DISABLED:
            self.hasher.verify_password(request.password, self._dummy)
            return AuthenticationResult(False, self.INVALID)
        if record.locked_until and record.locked_until > now:
            self.hasher.verify_password(request.password, self._dummy)
            return AuthenticationResult(False, self.UNAVAILABLE, temporarily_unavailable=True)
        stored = PasswordHashDTO(record.password_hash, record.password_salt, record.password_algorithm, record.password_parameters)
        if not self.hasher.verify_password(request.password, stored):
            attempts = record.failed_attempts + 1
            locked = now + timedelta(seconds=self.policy.lockout_seconds) if attempts >= self.policy.max_failed_attempts else None
            self.repository.update_login_failure(record.user_id, failed_attempts=attempts, locked_until=locked, now=now)
            return AuthenticationResult(False, self.UNAVAILABLE if locked else self.INVALID, temporarily_unavailable=locked is not None)
        user = self.repository.update_login_success(record.user_id, now=now)
        return AuthenticationResult(True, "Inicio de sesión correcto.", user)

    def change_password(self, user_id: str, new_password: str) -> None:
        self.repository.change_password_hash(user_id, self.hasher.hash_password(new_password), now=self._now())
