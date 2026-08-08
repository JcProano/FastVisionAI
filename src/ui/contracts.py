"""Safe public DTOs and states for the local experimental face UI."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class UIState(str, Enum):
    STARTING = "starting"
    MONITORING = "monitoring"
    NO_FACE = "no_face"
    MULTIPLE_FACES = "multiple_faces"
    FORM_OPEN = "form_open"
    AWAITING_CONSENT = "awaiting_consent"
    ENROLLING = "enrolling"
    ENROLLMENT_COMPLETE = "enrollment_complete"
    ENROLLMENT_REJECTED = "enrollment_rejected"
    CANCELLED = "cancelled"
    ERROR = "error"
    STOPPING = "stopping"
    CLOSED = "closed"


class UIErrorCode(str, Enum):
    CAMERA_ERROR = "camera_error"
    INFERENCE_ERROR = "inference_error"
    MATCHER_ERROR = "matcher_error"
    ENROLLMENT_ERROR = "enrollment_error"
    PERSISTENCE_ERROR = "persistence_error"
    THUMBNAIL_ERROR = "thumbnail_error"


@dataclass(frozen=True, slots=True)
class VisualFrameDTO:
    """One copied RGB presentation buffer; never persisted by the UI layer."""
    width: int
    height: int
    rgb_bytes: bytes
    sequence_id: int

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("visual frame dimensions must be positive")
        if type(self.rgb_bytes) is not bytes or len(self.rgb_bytes) != self.width * self.height * 3:
            raise ValueError("visual frame must contain owned packed RGB bytes")


@dataclass(frozen=True, slots=True)
class RuntimeStatusDTO:
    camera_state: str
    runtime_state: str
    detector_model_state: str
    embedding_model_state: str


@dataclass(frozen=True, slots=True)
class RegistrationFormData:
    first_name: str
    last_name: str
    display_name: str
    person_id: str
    external_identifier: str | None
    consent_confirmed: bool
    persist_locally: bool


@dataclass(frozen=True, slots=True)
class MonitoringDTO:
    state: UIState
    message: str
    candidate_display_name: str | None
    similarity: float | None
    automatic_decision: str
    registration_enabled: bool
    quality_score: float | None = None
    quality_band: str | None = None
    recognition_state: str = "NOT_EVALUATED"
    candidate_person_id: str | None = None


@dataclass(frozen=True, slots=True)
class EnrollmentProgressDTO:
    state: UIState
    instruction: str
    accepted_samples: int
    target_samples: int
    current_reasons: tuple[str, ...]
    quality_score: float | None
    quality_band: str | None
    cancellation_enabled: bool


@dataclass(frozen=True, slots=True)
class EnrollmentResultDTO:
    state: UIState
    person_id: str
    first_name: str
    last_name: str
    display_name: str
    templates_registered: int
    templates_rejected: int
    average_quality: float
    minimum_quality: float
    maximum_quality: float
    enrollment_status: str
    persistence_requested: bool
    persistence_succeeded: bool | None
    message: str


@dataclass(frozen=True, slots=True)
class ErrorDTO:
    state: UIState
    operation: UIErrorCode
    message: str
    recoverable: bool
