"""Safe scalar contracts for detection observations and persisted events."""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class DetectionEventValidationError(ValueError): pass
class DetectionEventRepositoryError(RuntimeError): pass
class DetectionEventPersistenceError(RuntimeError): pass


class DetectionEventType(str, Enum):
    REGISTERED_CANDIDATE = "REGISTERED_CANDIDATE"
    UNREGISTERED = "UNREGISTERED"
    INCOMPATIBLE = "INCOMPATIBLE"
    MULTIPLE_FACES = "MULTIPLE_FACES"


@dataclass(frozen=True, slots=True)
class DetectionEventInput:
    event_type: DetectionEventType
    person_id: str | None
    timestamp: datetime
    camera_id: str | None
    display_name_snapshot: str | None
    similarity: float | None
    quality_score: float | None
    recognition_state: str
    administrative_status: str | None
    session_id: str | None

    def __post_init__(self) -> None:
        if self.timestamp.tzinfo is None:
            raise DetectionEventValidationError("timestamp must be timezone-aware")
        if self.event_type is DetectionEventType.REGISTERED_CANDIDATE:
            if not self.person_id:
                raise DetectionEventValidationError("registered candidate requires person_id")
            if self.recognition_state != "NOT_EVALUATED":
                raise DetectionEventValidationError("candidate observation must be NOT_EVALUATED")
        elif self.person_id is not None:
            raise DetectionEventValidationError("aggregate event cannot contain person_id")
        for value in (self.similarity, self.quality_score):
            if value is not None and not math.isfinite(value):
                raise DetectionEventValidationError("event metric must be finite")


@dataclass(frozen=True, slots=True)
class DetectionEventRecord:
    event_id: str
    person_id: str | None
    event_type: DetectionEventType
    timestamp: datetime
    camera_id: str | None
    display_name_snapshot: str | None
    similarity: float | None
    quality_score: float | None
    recognition_state: str
    administrative_status: str | None
    session_id: str | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class DetectionEventDTO:
    event_id: str
    person_id: str | None
    event_type: str
    timestamp: datetime
    camera_id: str | None
    display_name: str | None
    masked_cedula: str | None
    similarity: float | None
    quality_score: float | None
    recognition_state: str
    administrative_status: str | None


@dataclass(frozen=True, slots=True)
class DetectionEventQuery:
    date_from: datetime | None = None
    date_to: datetime | None = None
    person_id: str | None = None
    event_type: DetectionEventType | None = None
    limit: int = 100
    offset: int = 0
    camera_id: str | None = None
    administrative_status: str | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.limit <= 500 or self.offset < 0:
            raise DetectionEventValidationError("query bounds are invalid")
        for value in (self.date_from, self.date_to):
            if value is not None and value.tzinfo is None:
                raise DetectionEventValidationError("query dates must be timezone-aware")
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise DetectionEventValidationError("date range is invalid")


@dataclass(frozen=True, slots=True)
class DetectionEventWriteResult:
    success: bool
    recorded: bool
    event: DetectionEventRecord | None
    message: str
