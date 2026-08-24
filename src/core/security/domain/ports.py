"""Dependency-inversion ports for security workflows."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from .models import (
    PasswordHashDTO,
    UserCreateRequest,
    UserDTO,
    UserRecord,
    UserStatus,
    UserUpdateRequest,
)


class UserRepositoryPort(Protocol):
    def bootstrap_admin(
        self, request: UserCreateRequest, password: PasswordHashDTO
    ) -> UserDTO: ...
    def create_user(
        self, request: UserCreateRequest, password: PasswordHashDTO
    ) -> UserDTO: ...
    def get_by_user_id(self, user_id: str) -> UserRecord | None: ...
    def get_by_username(self, username: str) -> UserRecord | None: ...
    def list_users(self) -> tuple[UserDTO, ...]: ...
    def count_users(self) -> int: ...
    def update_user(self, request: UserUpdateRequest) -> UserDTO: ...
    def set_status(self, user_id: str, status: UserStatus) -> UserDTO: ...
    def update_login_success(
        self, user_id: str, *, now: datetime | None = None
    ) -> UserDTO: ...
    def update_login_failure(
        self,
        user_id: str,
        *,
        failed_attempts: int,
        locked_until: datetime | None,
        now: datetime | None = None,
    ) -> None: ...
    def change_password_hash(
        self,
        user_id: str,
        password: PasswordHashDTO,
        *,
        now: datetime | None = None,
    ) -> None: ...


class PasswordHasherPort(Protocol):
    def hash_password(self, password: str) -> PasswordHashDTO: ...
    def verify_password(self, password: str, stored: PasswordHashDTO) -> bool: ...
