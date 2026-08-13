"""Typed, non-biometric contracts for administrative auditing."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from types import MappingProxyType
from typing import Mapping


class AuditError(RuntimeError): pass
class AuditValidationError(ValueError): pass
class AuditRepositoryError(AuditError): pass
class AuditExportError(AuditError): pass


class AuditAction(str, Enum):
    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_FAILURE = "LOGIN_FAILURE"
    LOGOUT = "LOGOUT"
    PASSWORD_CHANGED = "PASSWORD_CHANGED"
    PASSWORD_RESET = "PASSWORD_RESET"
    USER_CREATED = "USER_CREATED"
    USER_UPDATED = "USER_UPDATED"
    USER_ROLE_CHANGED = "USER_ROLE_CHANGED"
    USER_ENABLED = "USER_ENABLED"
    USER_DISABLED = "USER_DISABLED"
    PERSON_CREATED = "PERSON_CREATED"
    PERSON_UPDATED = "PERSON_UPDATED"
    PERSON_STATUS_CHANGED = "PERSON_STATUS_CHANGED"
    MANUAL_CHECK_IN = "MANUAL_CHECK_IN"
    MANUAL_CHECK_OUT = "MANUAL_CHECK_OUT"
    REPORT_EXPORTED = "REPORT_EXPORTED"
    CONFIG_VALIDATED = "CONFIG_VALIDATED"
    CONFIG_SAVED = "CONFIG_SAVED"
    CONFIG_RELOADED = "CONFIG_RELOADED"
    CONFIG_IMPORT_REJECTED = "CONFIG_IMPORT_REJECTED"
    BACKUP_STARTED = "BACKUP_STARTED"
    BACKUP_SUCCESS = "BACKUP_SUCCESS"
    BACKUP_FAILED = "BACKUP_FAILED"
    VERIFY_SUCCESS = "VERIFY_SUCCESS"
    VERIFY_FAILED = "VERIFY_FAILED"
    RESTORE_STARTED = "RESTORE_STARTED"
    RESTORE_SUCCESS = "RESTORE_SUCCESS"
    RESTORE_FAILED = "RESTORE_FAILED"
    SYSTEM_HEALTH_VIEWED = "SYSTEM_HEALTH_VIEWED"


class AuditEntityType(str, Enum):
    SESSION = "SESSION"
    USER = "USER"
    PERSON = "PERSON"
    ATTENDANCE = "ATTENDANCE"
    REPORT = "REPORT"
    CONFIGURATION = "CONFIGURATION"
    BACKUP = "BACKUP"
    SYSTEM_HEALTH = "SYSTEM_HEALTH"


@dataclass(frozen=True, slots=True)
class AuditRecord:
    audit_id: str
    timestamp_utc: datetime
    actor_user_id: str | None
    actor_role: str | None
    action: AuditAction
    entity_type: AuditEntityType
    entity_id: str | None
    success: bool
    message: str
    source: str
    session_id: str | None
    metadata: Mapping[str, str | int | float | bool | None] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True, slots=True)
class AuditRecordDTO:
    audit_id: str
    timestamp_utc: datetime
    actor_user_id: str | None
    actor_role: str | None
    action: str
    entity_type: str
    entity_id: str | None
    success: bool
    message: str
    source: str
    session_id: str | None


@dataclass(frozen=True, slots=True)
class AuditQuery:
    date_from: datetime | None = None
    date_to: datetime | None = None
    action: AuditAction | None = None
    actor_user_id: str | None = None
    actor_role: str | None = None
    entity_type: AuditEntityType | None = None
    entity_id: str | None = None
    success: bool | None = None
    limit: int = 200
    offset: int = 0

    def __post_init__(self) -> None:
        if self.limit <= 0 or self.offset < 0:
            raise AuditValidationError("audit query pagination is invalid")
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise AuditValidationError("audit query dates are invalid")


@dataclass(frozen=True, slots=True)
class AuditSummaryDTO:
    total: int
    successes: int
    failures: int
    latest_timestamp_utc: datetime | None


@dataclass(frozen=True, slots=True)
class AuditOperationResult:
    success: bool
    message: str
    audit_id: str | None = None

