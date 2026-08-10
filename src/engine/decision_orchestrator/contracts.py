"""Safe proposal-only contracts for the application decision boundary."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class DecisionOrchestratorValidationError(ValueError):
    pass


class DecisionState(str, Enum):
    NOT_EVALUATED = "NOT_EVALUATED"
    OBSERVATION_ONLY = "OBSERVATION_ONLY"
    CANDIDATE_STABLE = "CANDIDATE_STABLE"
    POLICY_ELIGIBLE = "POLICY_ELIGIBLE"
    ACTIONS_DISABLED = "ACTIONS_DISABLED"
    BLOCKED_BY_POLICY = "BLOCKED_BY_POLICY"
    BLOCKED_BY_ADMIN_STATUS = "BLOCKED_BY_ADMIN_STATUS"
    AMBIGUOUS = "AMBIGUOUS"
    INCOMPATIBLE = "INCOMPATIBLE"
    NO_CANDIDATE = "NO_CANDIDATE"


class ProposedAction(str, Enum):
    SHOW_REGISTERED_POPUP = "SHOW_REGISTERED_POPUP"
    SHOW_UNREGISTERED_POPUP = "SHOW_UNREGISTERED_POPUP"
    LOG_DETECTION_EVENT = "LOG_DETECTION_EVENT"
    PROPOSE_ATTENDANCE = "PROPOSE_ATTENDANCE"
    NONE = "NONE"


ADMINISTRATIVE_STATUSES = frozenset({
    "ACTIVE", "DISABLED", "PENDING_BIOMETRIC", "LEGACY_BIOMETRIC_ONLY",
    "NOT_FOUND",
})


@dataclass(frozen=True, slots=True)
class DecisionOrchestratorInput:
    face_count: int
    person_id: str | None
    recognition_state: str
    similarity: float | None
    stability_state: str
    identification_policy_state: str
    policy_eligible: bool
    administrative_status: str | None
    quality_score: float | None
    run_id: str
    session_id: str
    timestamp: datetime

    def __post_init__(self) -> None:
        if self.face_count < 0:
            raise DecisionOrchestratorValidationError("face_count cannot be negative")
        if self.person_id is not None and not self.person_id.strip():
            raise DecisionOrchestratorValidationError("person_id cannot be blank")
        if not self.recognition_state.strip() or not self.stability_state.strip():
            raise DecisionOrchestratorValidationError("observation states are required")
        if not self.identification_policy_state.strip():
            raise DecisionOrchestratorValidationError("identification policy state is required")
        if self.similarity is not None and not _bounded(self.similarity, -1.0, 1.0):
            raise DecisionOrchestratorValidationError("similarity must be within [-1, 1]")
        if self.quality_score is not None and not _bounded(self.quality_score, 0.0, 100.0):
            raise DecisionOrchestratorValidationError("quality score must be within [0, 100]")
        if self.administrative_status not in ADMINISTRATIVE_STATUSES | {None}:
            raise DecisionOrchestratorValidationError("administrative status is invalid")
        if not self.run_id.strip() or not self.session_id.strip() or self.timestamp.tzinfo is None:
            raise DecisionOrchestratorValidationError(
                "run_id, session_id and aware timestamp are required"
            )


@dataclass(frozen=True, slots=True)
class DecisionOrchestratorResult:
    state: DecisionState
    evaluated: bool
    person_id: str | None
    proposed_actions: tuple[ProposedAction, ...]
    blocked_actions: tuple[ProposedAction, ...]
    reasons: tuple[str, ...]
    automatic_actions_enabled: bool
    policy_name: str
    policy_version: str
    timestamp: datetime

    def __post_init__(self) -> None:
        if ProposedAction.NONE in self.proposed_actions and len(self.proposed_actions) != 1:
            raise DecisionOrchestratorValidationError("NONE cannot accompany real proposals")
        if ProposedAction.NONE in self.blocked_actions:
            raise DecisionOrchestratorValidationError("NONE cannot be blocked")
        if len(set(self.proposed_actions)) != len(self.proposed_actions):
            raise DecisionOrchestratorValidationError("proposed actions contain duplicates")
        if len(set(self.blocked_actions)) != len(self.blocked_actions):
            raise DecisionOrchestratorValidationError("blocked actions contain duplicates")


def _bounded(value: float, minimum: float, maximum: float) -> bool:
    return math.isfinite(value) and minimum <= value <= maximum
