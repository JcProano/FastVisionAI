"""PII-only contracts for the local person database."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from .validators import (
    EcuadorianCedulaValidator, normalize_phone, optional_text, required_text,
    validate_birth_date, validate_email, validate_person_id,
)


class PersonStatus(str, Enum):
    PENDING_BIOMETRIC = "PENDING_BIOMETRIC"
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


@dataclass(frozen=True, slots=True)
class PersonCreateRequest:
    person_id: str
    cedula: str
    first_name: str
    last_name: str
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    birth_date: str | None = None
    sex: str | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "person_id", validate_person_id(self.person_id))
        object.__setattr__(self, "cedula", EcuadorianCedulaValidator.validate(self.cedula))
        object.__setattr__(self, "first_name", required_text(self.first_name, "first_name"))
        object.__setattr__(self, "last_name", required_text(self.last_name, "last_name"))
        object.__setattr__(self, "address", optional_text(self.address, "address"))
        object.__setattr__(self, "phone", normalize_phone(self.phone))
        object.__setattr__(self, "email", validate_email(self.email))
        object.__setattr__(self, "birth_date", validate_birth_date(self.birth_date))
        object.__setattr__(self, "sex", optional_text(self.sex, "sex", 40))
        object.__setattr__(self, "notes", optional_text(self.notes, "notes", 2_000))


@dataclass(frozen=True, slots=True)
class PersonUpdateRequest:
    person_id: str
    first_name: str | None = None
    last_name: str | None = None
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    birth_date: str | None = None
    sex: str | None = None
    notes: str | None = None
    clear_fields: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(self, "person_id", validate_person_id(self.person_id))
        if self.first_name is not None:
            object.__setattr__(self, "first_name", required_text(self.first_name, "first_name"))
        if self.last_name is not None:
            object.__setattr__(self, "last_name", required_text(self.last_name, "last_name"))
        if self.address is not None:
            object.__setattr__(self, "address", optional_text(self.address, "address"))
        if self.phone is not None:
            object.__setattr__(self, "phone", normalize_phone(self.phone))
        if self.email is not None:
            object.__setattr__(self, "email", validate_email(self.email))
        if self.birth_date is not None:
            object.__setattr__(self, "birth_date", validate_birth_date(self.birth_date))
        if self.sex is not None:
            object.__setattr__(self, "sex", optional_text(self.sex, "sex", 40))
        if self.notes is not None:
            object.__setattr__(self, "notes", optional_text(self.notes, "notes", 2_000))
        allowed_clear = {"address", "phone", "email", "birth_date", "sex", "notes"}
        if not self.clear_fields <= allowed_clear:
            raise ValueError("clear_fields contains a required or unknown field")


@dataclass(frozen=True, slots=True)
class PersonRecord:
    person_id: str
    cedula: str
    first_name: str
    last_name: str
    address: str | None
    phone: str | None
    email: str | None
    birth_date: str | None
    sex: str | None
    notes: str | None
    status: PersonStatus
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class PersonSearchQuery:
    cedula: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    phone: str | None = None
    email: str | None = None
    status: PersonStatus | None = None
    limit: int = 100
    offset: int = 0

    def __post_init__(self) -> None:
        if not 1 <= self.limit <= 1_000 or self.offset < 0:
            raise ValueError("search limit or offset is invalid")


@dataclass(frozen=True, slots=True)
class PersonDatabaseStats:
    total: int
    pending_biometric: int
    active: int
    disabled: int
    schema_version: int
