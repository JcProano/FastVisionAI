"""Immutable contracts for the independent operator security domain."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import re, uuid

class SecurityError(RuntimeError): pass
class SecurityValidationError(ValueError): pass
class UserRepositoryError(SecurityError): pass
class DuplicateUsernameError(UserRepositoryError): pass
class UserNotFoundError(UserRepositoryError): pass
class BootstrapError(SecurityError): pass

class UserStatus(str, Enum): ACTIVE="ACTIVE"; DISABLED="DISABLED"; LOCKED="LOCKED"
class UserRole(str, Enum): ADMIN="ADMIN"; OPERATOR="OPERATOR"; AUDITOR="AUDITOR"; VIEWER="VIEWER"

class AuthorizationPermission(str, Enum):
    VIEW_DASHBOARD="VIEW_DASHBOARD"; VIEW_PEOPLE="VIEW_PEOPLE"; EDIT_PERSON="EDIT_PERSON"
    CHANGE_PERSON_STATUS="CHANGE_PERSON_STATUS"; ENROLL_PERSON="ENROLL_PERSON"
    VIEW_REPORTS="VIEW_REPORTS"; EXPORT_REPORTS="EXPORT_REPORTS"
    VIEW_ATTENDANCE="VIEW_ATTENDANCE"; MANUAL_ATTENDANCE="MANUAL_ATTENDANCE"
    VIEW_DETECTION_HISTORY="VIEW_DETECTION_HISTORY"; VIEW_AUDIT="VIEW_AUDIT"
    EXPORT_AUDIT="EXPORT_AUDIT"; VIEW_SETTINGS="VIEW_SETTINGS"; EDIT_SETTINGS="EDIT_SETTINGS"
    MANAGE_USERS="MANAGE_USERS"; BACKUP="BACKUP"; RESTORE="RESTORE"; VIEW_SYSTEM_HEALTH="VIEW_SYSTEM_HEALTH"
    APPLICATION_EXIT="APPLICATION_EXIT"

class AuthorizationReason(str, Enum):
    AUTHORIZED="AUTHORIZED"; PERMISSION_DENIED="PERMISSION_DENIED"
    UNKNOWN_ROLE="UNKNOWN_ROLE"; UNKNOWN_PERMISSION="UNKNOWN_PERMISSION"
    AUTHORIZATION_DISABLED="AUTHORIZATION_DISABLED"; NOT_AUTHENTICATED="NOT_AUTHENTICATED"

@dataclass(frozen=True, slots=True)
class PasswordPolicy:
    minimum_length: int = 10; maximum_length: int = 128
    def __post_init__(self):
        if self.minimum_length <= 0 or self.maximum_length < self.minimum_length:
            raise SecurityValidationError("password policy bounds are invalid")
    def validate(self, password: str) -> None:
        if not isinstance(password, str) or not self.minimum_length <= len(password) <= self.maximum_length:
            raise SecurityValidationError("password length is invalid")
        if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
            raise SecurityValidationError("password must contain a letter and a number")

@dataclass(frozen=True, slots=True)
class PasswordHashDTO:
    password_hash: bytes = field(repr=False); password_salt: bytes = field(repr=False)
    algorithm: str; parameters: str

@dataclass(frozen=True, slots=True)
class UserRecord:
    user_id: str; username: str; display_name: str
    password_hash: bytes = field(repr=False); password_salt: bytes = field(repr=False)
    password_algorithm: str = field(repr=False); password_parameters: str = field(repr=False)
    role: UserRole = UserRole.VIEWER; status: UserStatus = UserStatus.ACTIVE
    failed_attempts: int = 0; locked_until: datetime | None = None
    last_login_at: datetime | None = None; password_changed_at: datetime | None = None
    created_at: datetime | None = None; updated_at: datetime | None = None

@dataclass(frozen=True, slots=True)
class UserDTO:
    user_id: str; username: str; display_name: str; role: UserRole; status: UserStatus
    failed_attempts: int; locked_until: datetime | None; last_login_at: datetime | None
    password_changed_at: datetime | None; created_at: datetime; updated_at: datetime

@dataclass(frozen=True, slots=True)
class UserCreateRequest:
    user_id: str; username: str; display_name: str; role: UserRole
    def __post_init__(self):
        object.__setattr__(self, "user_id", canonical_uuid(self.user_id))
        object.__setattr__(self, "username", normalize_username(self.username))
        object.__setattr__(self, "display_name", safe_name(self.display_name))

@dataclass(frozen=True, slots=True)
class UserUpdateRequest:
    user_id: str; display_name: str | None = None; role: UserRole | None = None
    def __post_init__(self):
        object.__setattr__(self, "user_id", canonical_uuid(self.user_id))
        if self.display_name is not None: object.__setattr__(self,"display_name",safe_name(self.display_name))

@dataclass(frozen=True, slots=True)
class PasswordChangeRequest:
    user_id: str
    def __post_init__(self): object.__setattr__(self,"user_id",canonical_uuid(self.user_id))

@dataclass(frozen=True, slots=True)
class AuthenticationRequest:
    username: str; password: str = field(repr=False)

@dataclass(frozen=True, slots=True)
class AuthenticationResult:
    success: bool; message: str; user: UserDTO | None = None; temporarily_unavailable: bool = False

@dataclass(frozen=True, slots=True)
class AuthenticatedSessionDTO:
    session_id: str; user_id: str; username: str; display_name: str; role: UserRole
    authenticated_at: datetime; last_activity_at: datetime

@dataclass(frozen=True, slots=True)
class AuthorizationContext:
    user_id: str | None; role: UserRole | None; authenticated: bool; session_id: str | None

@dataclass(frozen=True, slots=True)
class AuthorizationResult:
    evaluated: bool; allowed: bool; role: str | None; permission: str | None; reason: AuthorizationReason

@dataclass(frozen=True, slots=True)
class UserOperationResult:
    success: bool; operation: str; message: str; user_id: str | None = None; user: UserDTO | None = None

def canonical_uuid(value: str) -> str:
    try: parsed=uuid.UUID(value.strip())
    except Exception as exc: raise SecurityValidationError("user_id is invalid") from exc
    if str(parsed) != value.strip().lower(): raise SecurityValidationError("user_id is invalid")
    return str(parsed)

def normalize_username(value: str) -> str:
    cleaned=value.strip().casefold()
    if not re.fullmatch(r"[a-z0-9._-]{3,64}", cleaned): raise SecurityValidationError("username is invalid")
    return cleaned

def safe_name(value: str) -> str:
    cleaned=" ".join(value.split())
    if not cleaned or len(cleaned)>120 or any(ord(c)<32 for c in cleaned): raise SecurityValidationError("display name is invalid")
    return cleaned

def public_user(record: UserRecord) -> UserDTO:
    assert record.created_at and record.updated_at
    return UserDTO(record.user_id,record.username,record.display_name,record.role,record.status,
                   record.failed_attempts,record.locked_until,record.last_login_at,
                   record.password_changed_at,record.created_at,record.updated_at)
