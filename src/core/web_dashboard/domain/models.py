"""Framework-independent state for one local web enrollment flow."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Mapping


class WebEnrollmentError(ValueError):
    pass


class WebEnrollmentStage(str, Enum):
    IDLE = "IDLE"
    PERSON = "PERSON"
    PREPARATION = "PREPARATION"
    CAPTURE = "CAPTURE"
    VALIDATION = "VALIDATION"
    PHOTO = "PHOTO"
    PHOTO_CAPTURE = "PHOTO_CAPTURE"
    PHOTO_CONFIRMATION = "PHOTO_CONFIRMATION"
    CONFIRMATION = "CONFIRMATION"
    COMPLETE = "COMPLETE"


@dataclass(frozen=True, slots=True)
class WebEnrollmentState:
    stage: WebEnrollmentStage = WebEnrollmentStage.IDLE
    summary: Mapping[str, str] = field(default_factory=dict)
    result: object | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "summary", MappingProxyType(dict(self.summary)))

    @property
    def active(self) -> bool:
        return self.stage is not WebEnrollmentStage.IDLE
