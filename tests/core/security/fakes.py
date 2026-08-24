"""In-memory ports for security application tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from src.core.security.domain import (
    PasswordHashDTO,
    UserCreateRequest,
    UserDTO,
    UserRecord,
    UserStatus,
    UserUpdateRequest,
    public_user,
)

MOMENT = datetime(2026, 1, 1, tzinfo=timezone.utc)


def user_record(request: UserCreateRequest) -> UserRecord:
    return UserRecord(
        request.user_id,
        request.username,
        request.display_name,
        b"valid",
        b"salt",
        "fake",
        "{}",
        request.role,
        created_at=MOMENT,
        updated_at=MOMENT,
    )


class InMemoryUserRepository:
    def __init__(self) -> None:
        self.records: dict[str, UserRecord] = {}
        self.password_changes: list[tuple[str, PasswordHashDTO, datetime | None]] = []

    def bootstrap_admin(
        self, request: UserCreateRequest, password: PasswordHashDTO
    ) -> UserDTO:
        if self.records:
            raise RuntimeError("already bootstrapped")
        return self.create_user(request, password)

    def create_user(
        self, request: UserCreateRequest, password: PasswordHashDTO
    ) -> UserDTO:
        record = replace(
            user_record(request),
            password_hash=password.password_hash,
            password_salt=password.password_salt,
            password_algorithm=password.algorithm,
            password_parameters=password.parameters,
        )
        self.records[record.user_id] = record
        return public_user(record)

    def get_by_user_id(self, user_id: str) -> UserRecord | None:
        return self.records.get(user_id)

    def get_by_username(self, username: str) -> UserRecord | None:
        return next(
            (
                record
                for record in self.records.values()
                if record.username == username.casefold()
            ),
            None,
        )

    def list_users(self) -> tuple[UserDTO, ...]:
        return tuple(public_user(record) for record in self.records.values())

    def count_users(self) -> int:
        return len(self.records)

    def update_user(self, request: UserUpdateRequest) -> UserDTO:
        current = self.records[request.user_id]
        updated = replace(
            current,
            display_name=request.display_name or current.display_name,
            role=request.role or current.role,
        )
        self.records[request.user_id] = updated
        return public_user(updated)

    def set_status(self, user_id: str, status: UserStatus) -> UserDTO:
        updated = replace(self.records[user_id], status=status)
        self.records[user_id] = updated
        return public_user(updated)

    def update_login_success(
        self, user_id: str, *, now: datetime | None = None
    ) -> UserDTO:
        updated = replace(
            self.records[user_id],
            failed_attempts=0,
            locked_until=None,
            last_login_at=now,
        )
        self.records[user_id] = updated
        return public_user(updated)

    def update_login_failure(
        self,
        user_id: str,
        *,
        failed_attempts: int,
        locked_until: datetime | None,
        now: datetime | None = None,
    ) -> None:
        self.records[user_id] = replace(
            self.records[user_id],
            failed_attempts=failed_attempts,
            locked_until=locked_until,
            updated_at=now,
        )

    def change_password_hash(
        self,
        user_id: str,
        password: PasswordHashDTO,
        *,
        now: datetime | None = None,
    ) -> None:
        self.password_changes.append((user_id, password, now))


class FakePasswordHasher:
    def __init__(self) -> None:
        self.verifications: list[str] = []

    def hash_password(self, password: str) -> PasswordHashDTO:
        return PasswordHashDTO(password.encode(), b"salt", "fake", "{}")

    def verify_password(self, password: str, stored: PasswordHashDTO) -> bool:
        self.verifications.append(password)
        return password.encode() == stored.password_hash
