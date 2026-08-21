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
    ENROLLMENT_CAPTURE = "enrollment_capture"
    ROLLBACK = "rollback"
    CAPTURE_PERSON_PHOTO = "capture_person_photo"
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
    camera_switch_allowed: bool = True
    camera_source_name: str = "N/D"
    camera_source_type: str = "N/D"


@dataclass(frozen=True, slots=True)
class RegistrationFormData:
    first_name: str
    last_name: str
    display_name: str
    person_id: str
    external_identifier: str | None
    consent_confirmed: bool
    persist_locally: bool
    cedula: str | None = None
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    birth_date: str | None = None
    sex: str | None = None
    notes: str | None = None


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
    evaluated: bool | None = None
    match_threshold: float | None = None


@dataclass(frozen=True, slots=True)
class EnrollmentConflictDTO:
    """Safe civil conflict projection; contains no cedula or biometric payload."""
    state: UIState
    person_id: str
    person_status: str
    message: str
    can_view_person: bool
    can_add_samples: bool
    can_resume: bool = False
    display_name: str | None = None
    thumbnail_available: bool = False
    template_count: int = 0
    can_reactivate: bool = False


@dataclass(frozen=True, slots=True)
class PersonPhotoCaptureDTO:
    state: UIState
    person_id: str
    message: str
    quality_score: float | None
    ready: bool
    review: bool
    replace_existing: bool
    image_bytes: bytes | None = None
    stability_observations: int = 0
    stability_required: int = 0


@dataclass(frozen=True, slots=True)
class StabilityDTO:
    """Ephemeral scalar projection; temporal continuity is not identity."""
    state: str
    person_id: str | None
    observations_count: int
    required_observations: int
    stable_duration_seconds: float
    required_duration_seconds: float
    current_similarity: float | None
    average_similarity: float | None
    reason: str


@dataclass(frozen=True, slots=True)
class IdentificationPolicyDTO:
    """Safe informational projection; never an identity or action decision."""
    state: str
    evaluated: bool
    eligible: bool
    person_id: str | None
    reasons: tuple[str, ...]
    similarity: float | None
    quality_score: float | None
    stability_state: str
    administrative_status: str | None
    policy_name: str
    policy_version: str
    automatic_actions_enabled: bool


@dataclass(frozen=True, slots=True)
class DecisionOrchestratorDTO:
    """Proposal-only UI projection; it contains no executed actions."""
    state: str
    evaluated: bool
    person_id: str | None
    proposed_actions: tuple[str, ...]
    blocked_actions: tuple[str, ...]
    reasons: tuple[str, ...]
    automatic_actions_enabled: bool
    policy_name: str
    policy_version: str


@dataclass(frozen=True, slots=True)
class ActionExecutorDTO:
    """Safe projection of controlled execution; contains no adapter context."""
    state: str
    evaluated: bool
    requested_actions: tuple[str, ...]
    executed_actions: tuple[str, ...]
    skipped_actions: tuple[str, ...]
    failed_actions: tuple[str, ...]
    reasons: tuple[str, ...]
    automatic_execution_enabled: bool
    policy_name: str
    policy_version: str


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
    frame_id: int | None = None


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
    coordination_state: str | None = None


@dataclass(frozen=True, slots=True)
class ErrorDTO:
    state: UIState
    operation: UIErrorCode
    message: str
    recoverable: bool
