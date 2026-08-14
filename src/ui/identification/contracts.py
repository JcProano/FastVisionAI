"""Safe presentation contracts for experimental identification popups."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol

from src.ui.thumbnails import ThumbnailDTO


class IdentificationPopupType(str, Enum):
    REGISTERED_CANDIDATE = "REGISTERED_CANDIDATE"
    UNREGISTERED = "UNREGISTERED"
    SUPPRESSED = "SUPPRESSED"


@dataclass(frozen=True, slots=True)
class IdentificationPopupPolicy:
    enabled: bool = True
    registered_cooldown_seconds: float = 10.0
    unknown_cooldown_seconds: float = 10.0
    candidate_stability_frames: int = 3
    unknown_popup_timeout_seconds: float = 60.0
    registered_pause_seconds: float = 60.0

    def __post_init__(self) -> None:
        if self.registered_cooldown_seconds < 0 or self.unknown_cooldown_seconds < 0:
            raise ValueError("identification popup cooldowns must be non-negative")
        if self.candidate_stability_frames <= 0:
            raise ValueError("candidate_stability_frames must be positive")
        if self.unknown_popup_timeout_seconds <= 0:
            raise ValueError("unknown_popup_timeout_seconds must be positive")
        if self.registered_pause_seconds <= 0:
            raise ValueError("registered_pause_seconds must be positive")


@dataclass(frozen=True, slots=True)
class IdentificationPopupDTO:
    popup_type: IdentificationPopupType
    person_id: str | None
    display_name: str | None
    external_identifier: str | None
    similarity: float | None
    recognition_state: str
    thumbnail_available: bool
    message: str
    timestamp: datetime
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    civil_status: str | None = None
    department: str | None = None
    position: str | None = None
    company: str | None = None
    registered_at: datetime | None = None
    last_access_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class IdentityPersonDTO:
    person_id: str
    first_name: str
    last_name: str
    display_name: str
    external_identifier: str | None
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    status: str | None = None
    legacy_without_civil_data: bool = False
    department: str | None = None
    position: str | None = None
    company: str | None = None
    registered_at: datetime | None = None
    last_access_at: datetime | None = None


class IdentityInfoProvider(Protocol):
    """UI-only lookup boundary; never exposes gallery or biometric payloads."""

    def get_person(self, person_id: str) -> IdentityPersonDTO | None: ...

    def get_thumbnail(self, person_id: str) -> ThumbnailDTO: ...
