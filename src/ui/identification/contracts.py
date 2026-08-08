"""Safe presentation contracts for experimental identification popups."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Protocol

from src.ui.people.contracts import PersonSummaryDTO
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

    def __post_init__(self) -> None:
        if self.registered_cooldown_seconds < 0 or self.unknown_cooldown_seconds < 0:
            raise ValueError("identification popup cooldowns must be non-negative")
        if self.candidate_stability_frames <= 0:
            raise ValueError("candidate_stability_frames must be positive")


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


class IdentityInfoProvider(Protocol):
    """UI-only lookup boundary; never exposes gallery or biometric payloads."""

    def get_person(self, person_id: str) -> PersonSummaryDTO | None: ...

    def get_thumbnail(self, person_id: str) -> ThumbnailDTO: ...
