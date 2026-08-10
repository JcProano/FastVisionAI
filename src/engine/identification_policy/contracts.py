"""Safe contracts for administrative, informational policy evaluation."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class IdentificationPolicyValidationError(ValueError):
    pass


class IdentificationPolicyState(str, Enum):
    POLICY_NOT_EVALUATED = "POLICY_NOT_EVALUATED"
    ELIGIBLE = "ELIGIBLE"
    REJECTED_BY_POLICY = "REJECTED_BY_POLICY"
    AMBIGUOUS = "AMBIGUOUS"
    INCOMPATIBLE = "INCOMPATIBLE"
    NO_CANDIDATE = "NO_CANDIDATE"
    PERSON_NOT_ACTIVE = "PERSON_NOT_ACTIVE"
    INSUFFICIENT_STABILITY = "INSUFFICIENT_STABILITY"
    INSUFFICIENT_QUALITY = "INSUFFICIENT_QUALITY"


ADMINISTRATIVE_STATUSES = frozenset({
    "ACTIVE", "DISABLED", "PENDING_BIOMETRIC", "LEGACY_BIOMETRIC_ONLY",
    "NOT_FOUND",
})


@dataclass(frozen=True, slots=True)
class IdentificationPolicyInput:
    person_id: str | None
    recognition_state: str
    similarity: float | None
    stability_state: str
    stability_observations: int
    stability_duration_seconds: float
    quality_score: float | None
    administrative_status: str | None
    face_count: int
    run_id: str
    timestamp: datetime

    def __post_init__(self) -> None:
        if self.person_id is not None and not self.person_id.strip():
            raise IdentificationPolicyValidationError("person_id cannot be blank")
        if not self.recognition_state.strip() or not self.stability_state.strip():
            raise IdentificationPolicyValidationError("input states are required")
        if self.similarity is not None and not _bounded(self.similarity, -1.0, 1.0):
            raise IdentificationPolicyValidationError("similarity must be within [-1, 1]")
        if self.quality_score is not None and not _bounded(self.quality_score, 0.0, 100.0):
            raise IdentificationPolicyValidationError("quality_score must be within [0, 100]")
        if self.stability_observations < 0:
            raise IdentificationPolicyValidationError("stability observations cannot be negative")
        if not math.isfinite(self.stability_duration_seconds) or self.stability_duration_seconds < 0:
            raise IdentificationPolicyValidationError("stability duration is invalid")
        if self.face_count < 0:
            raise IdentificationPolicyValidationError("face_count cannot be negative")
        if self.administrative_status not in ADMINISTRATIVE_STATUSES | {None}:
            raise IdentificationPolicyValidationError("administrative status is invalid")
        if not self.run_id.strip() or self.timestamp.tzinfo is None:
            raise IdentificationPolicyValidationError("run_id and aware timestamp are required")


@dataclass(frozen=True, slots=True)
class IdentificationPolicyResult:
    state: IdentificationPolicyState
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
    timestamp: datetime


def _bounded(value: float, minimum: float, maximum: float) -> bool:
    return math.isfinite(value) and minimum <= value <= maximum
