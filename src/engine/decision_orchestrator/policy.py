"""Configuration for proposal generation; it never enables execution code."""

from dataclasses import dataclass

from .contracts import DecisionOrchestratorValidationError


@dataclass(frozen=True, slots=True)
class DecisionOrchestratorPolicy:
    enabled: bool = True
    automatic_actions_enabled: bool = False
    allow_registered_popup_proposal: bool = True
    allow_unregistered_popup_proposal: bool = True
    allow_detection_event_proposal: bool = True
    allow_attendance_proposal: bool = False
    require_stable_for_registered_popup: bool = True
    require_policy_eligible_for_attendance: bool = True
    require_active_person_for_attendance: bool = True
    policy_name: str = "decision_orchestrator_development"
    policy_version: str = "1.0"

    def __post_init__(self) -> None:
        if not self.policy_name.strip() or not self.policy_version.strip():
            raise DecisionOrchestratorValidationError("policy provenance is required")
