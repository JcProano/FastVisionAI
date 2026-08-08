"""Safe presentation contracts for a complete local person profile."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class PersonProfileStatus(str, Enum):
    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"
    PENDING_BIOMETRIC = "PENDING_BIOMETRIC"
    LEGACY_BIOMETRIC_ONLY = "LEGACY_BIOMETRIC_ONLY"
    NOT_FOUND = "NOT_FOUND"


@dataclass(frozen=True, slots=True)
class PersonProfileDTO:
    person_id: str | None
    cedula: str | None
    first_name: str | None
    last_name: str | None
    display_name: str | None
    address: str | None
    phone: str | None
    email: str | None
    birth_date: str | None
    sex: str | None
    notes: str | None
    administrative_status: PersonProfileStatus
    created_at: datetime | None
    updated_at: datetime | None
    thumbnail_available: bool
    thumbnail_bytes: bytes | None
    template_count: int
    scored_template_count: int
    average_quality_score: float | None
    minimum_quality_score: float | None
    maximum_quality_score: float | None
    first_template_at: datetime | None
    last_template_at: datetime | None
    legacy_biometric_record: bool
    profile_message: str


@dataclass(frozen=True, slots=True)
class PersonProfileOperationDTO:
    success: bool
    operation: str
    message: str
    profile: PersonProfileDTO | None = None

