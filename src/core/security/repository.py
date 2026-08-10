"""Transactional SQLite repository for administrative users only."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from .contracts import (
    DuplicateUsernameError, PasswordHashDTO, SecurityValidationError,
    UserCreateRequest, UserDTO, UserNotFoundError, UserRecord,
    UserRepositoryError, UserRole, UserStatus, UserUpdateRequest, public_user,
)
from .migrations import initialize_schema


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class LastActiveAdminError(UserRepositoryError):
    """Raised when a mutation would remove the final active administrator."""


class UserRepository:
    """Independent, thread-safe-by-connection users.db repository."""

    def __init__(self, path: Path, *, timeout: float = 5.0) -> None:
        self.path = Path(path)
        self.timeout = timeout

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=self.timeout)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> int:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._transaction() as connection:
                return initialize_schema(connection)
        except Exception as exc:
            if exc.__class__.__name__ == "SecurityMigrationError":
                raise
            raise UserRepositoryError("users database could not be initialized") from exc

    def bootstrap_admin(self, request: UserCreateRequest, password: PasswordHashDTO) -> UserDTO:
        if request.role is not UserRole.ADMIN:
            raise SecurityValidationError("bootstrap user must be ADMIN")
        with self._transaction() as connection:
            if connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]:
                from .contracts import BootstrapError
                raise BootstrapError("initial administrator already exists")
            self._insert(connection, request, password)
            return public_user(self._get_record(connection, request.user_id))

    def create_user(self, request: UserCreateRequest, password: PasswordHashDTO) -> UserDTO:
        try:
            with self._transaction() as connection:
                self._insert(connection, request, password)
                return public_user(self._get_record(connection, request.user_id))
        except sqlite3.IntegrityError as exc:
            if "username" in str(exc).lower():
                raise DuplicateUsernameError("username already exists") from exc
            raise UserRepositoryError("user could not be created") from exc

    def get_by_user_id(self, user_id: str) -> UserRecord | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        return self._row(row) if row else None

    def get_by_username(self, username: str) -> UserRecord | None:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM users WHERE username=? COLLATE NOCASE", (username.strip(),)).fetchone()
        return self._row(row) if row else None

    def list_users(self) -> tuple[UserDTO, ...]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM users ORDER BY username COLLATE NOCASE,user_id").fetchall()
        return tuple(public_user(self._row(row)) for row in rows)

    def count_users(self) -> int:
        with self._connect() as connection:
            return int(connection.execute("SELECT COUNT(*) FROM users").fetchone()[0])

    def update_user(self, request: UserUpdateRequest) -> UserDTO:
        with self._transaction() as connection:
            current = self._get_record(connection, request.user_id)
            new_role = request.role or current.role
            if current.role is UserRole.ADMIN and current.status is UserStatus.ACTIVE and new_role is not UserRole.ADMIN:
                self._ensure_other_admin(connection, current.user_id)
            connection.execute(
                "UPDATE users SET display_name=?,role=?,updated_at=? WHERE user_id=?",
                (request.display_name or current.display_name, new_role.value, _utc_now().isoformat(), current.user_id),
            )
            return public_user(self._get_record(connection, current.user_id))

    def set_status(self, user_id: str, status: UserStatus) -> UserDTO:
        with self._transaction() as connection:
            current = self._get_record(connection, user_id)
            if current.role is UserRole.ADMIN and current.status is UserStatus.ACTIVE and status is not UserStatus.ACTIVE:
                self._ensure_other_admin(connection, user_id)
            connection.execute(
                "UPDATE users SET status=?,updated_at=? WHERE user_id=?",
                (status.value, _utc_now().isoformat(), user_id),
            )
            return public_user(self._get_record(connection, user_id))

    def update_login_success(self, user_id: str, *, now: datetime | None = None) -> UserDTO:
        moment = now or _utc_now()
        with self._transaction() as connection:
            self._get_record(connection, user_id)
            connection.execute(
                "UPDATE users SET failed_attempts=0,locked_until=NULL,last_login_at=?,updated_at=? WHERE user_id=?",
                (moment.isoformat(), moment.isoformat(), user_id),
            )
            return public_user(self._get_record(connection, user_id))

    def update_login_failure(self, user_id: str, *, failed_attempts: int, locked_until: datetime | None, now: datetime | None = None) -> None:
        moment = now or _utc_now()
        with self._transaction() as connection:
            self._get_record(connection, user_id)
            connection.execute(
                "UPDATE users SET failed_attempts=?,locked_until=?,updated_at=? WHERE user_id=?",
                (failed_attempts, locked_until.isoformat() if locked_until else None, moment.isoformat(), user_id),
            )

    def change_password_hash(self, user_id: str, password: PasswordHashDTO, *, now: datetime | None = None) -> None:
        moment = now or _utc_now()
        with self._transaction() as connection:
            self._get_record(connection, user_id)
            connection.execute(
                """UPDATE users SET password_hash=?,password_salt=?,password_algorithm=?,
                   password_parameters=?,password_changed_at=?,failed_attempts=0,locked_until=NULL,updated_at=? WHERE user_id=?""",
                (password.password_hash, password.password_salt, password.algorithm, password.parameters,
                 moment.isoformat(), moment.isoformat(), user_id),
            )

    def _insert(self, connection: sqlite3.Connection, request: UserCreateRequest, password: PasswordHashDTO) -> None:
        moment = _utc_now().isoformat()
        try:
            connection.execute(
                """INSERT INTO users(user_id,username,display_name,password_hash,password_salt,
                password_algorithm,password_parameters,role,status,failed_attempts,locked_until,
                last_login_at,password_changed_at,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,0,NULL,NULL,?,?,?)""",
                (request.user_id, request.username, request.display_name, password.password_hash,
                 password.password_salt, password.algorithm, password.parameters, request.role.value,
                 UserStatus.ACTIVE.value, moment, moment, moment),
            )
        except sqlite3.IntegrityError as exc:
            if "username" in str(exc).lower():
                raise DuplicateUsernameError("username already exists") from exc
            raise

    @staticmethod
    def _ensure_other_admin(connection: sqlite3.Connection, excluded_id: str) -> None:
        count = connection.execute(
            "SELECT COUNT(*) FROM users WHERE role=? AND status=? AND user_id<>?",
            (UserRole.ADMIN.value, UserStatus.ACTIVE.value, excluded_id),
        ).fetchone()[0]
        if not count:
            raise LastActiveAdminError("last active administrator is protected")

    def _get_record(self, connection: sqlite3.Connection, user_id: str) -> UserRecord:
        row = connection.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
        if row is None:
            raise UserNotFoundError("user does not exist")
        return self._row(row)

    @staticmethod
    def _row(row: sqlite3.Row) -> UserRecord:
        try:
            return UserRecord(
                row["user_id"], row["username"], row["display_name"], bytes(row["password_hash"]),
                bytes(row["password_salt"]), row["password_algorithm"], row["password_parameters"],
                UserRole(row["role"]), UserStatus(row["status"]), int(row["failed_attempts"]),
                _parse(row["locked_until"]), _parse(row["last_login_at"]),
                _parse(row["password_changed_at"]), _parse(row["created_at"]), _parse(row["updated_at"]),
            )
        except Exception as exc:
            raise UserRepositoryError("stored user record is invalid") from exc
