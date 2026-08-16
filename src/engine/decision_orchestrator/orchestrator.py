"""Stateless, side-effect-free proposal orchestration."""

from __future__ import annotations

from .contracts import (
    DecisionOrchestratorInput, DecisionOrchestratorResult, DecisionState,
    ProposedAction,
)
from .policy import DecisionOrchestratorPolicy


class DecisionOrchestrator:
    """Return proposals only; no action execution path exists in this component."""

    __slots__ = ("policy",)

    def __init__(self, policy: DecisionOrchestratorPolicy | None = None) -> None:
        self.policy = policy or DecisionOrchestratorPolicy()

    def evaluate(self, value: DecisionOrchestratorInput) -> DecisionOrchestratorResult:
        policy = self.policy
        if not policy.enabled:
            return self._result(
                value, DecisionState.NOT_EVALUATED, (), (), ("orchestrator_disabled",),
                evaluated=False,
            )

        recognition = value.recognition_state.upper()
        stability = value.stability_state.upper()
        identification = value.identification_policy_state.upper()
        reasons: list[str] = []
        proposals: list[ProposedAction] = []
        blocked: list[ProposedAction] = []

        structural_state: DecisionState | None = None
        if value.face_count == 0:
            structural_state = DecisionState.NO_CANDIDATE
            reasons.append("no_candidate")
        elif value.face_count > 1:
            structural_state = DecisionState.AMBIGUOUS
            reasons.append("multiple_faces")
        elif recognition == "INCOMPATIBLE":
            structural_state = DecisionState.INCOMPATIBLE
            reasons.append("incompatible")

        relevant_observation = value.face_count > 0
        if (policy.allow_detection_event_proposal and relevant_observation
                and value.person_id is None):
            proposals.append(ProposedAction.LOG_DETECTION_EVENT)

        if structural_state is None and value.person_id is None:
            state = DecisionState.OBSERVATION_ONLY
            reasons.append("candidate_unregistered")
            unknown_stable = (
                value.face_count == 1
                and recognition in {"UNKNOWN", "NO_GALLERY", "NOT_EVALUATED"}
                and stability == "STABLE"
            )
            if policy.allow_unregistered_popup_proposal and unknown_stable:
                proposals.append(ProposedAction.SHOW_UNREGISTERED_POPUP)
            elif policy.allow_unregistered_popup_proposal:
                blocked.append(ProposedAction.SHOW_UNREGISTERED_POPUP)
                reasons.append("unregistered_observation_not_stable")
        elif structural_state is None:
            state = DecisionState.CANDIDATE_STABLE if stability == "STABLE" else DecisionState.OBSERVATION_ONLY
            if stability != "STABLE":
                reasons.append("observation_not_stable")
            if value.administrative_status != "ACTIVE":
                state = DecisionState.BLOCKED_BY_ADMIN_STATUS
                reasons.append("person_not_active")
            elif not value.policy_eligible or identification != "ELIGIBLE":
                state = DecisionState.BLOCKED_BY_POLICY
                reasons.append("identification_policy_not_eligible")
            elif stability == "STABLE":
                state = DecisionState.POLICY_ELIGIBLE
            registered_eligible = (
                value.face_count == 1
                and value.administrative_status == "ACTIVE"
                and value.policy_eligible
                and identification == "ELIGIBLE"
                and (not policy.require_stable_for_registered_popup
                     or stability == "STABLE")
            )
            registered_history_eligible = (
                value.face_count == 1
                and value.administrative_status == "ACTIVE"
                and value.policy_eligible
                and identification == "ELIGIBLE"
                and stability == "STABLE"
            )
            # NO_OBSERVATION preserves the explicitly tracker-less legacy mode;
            # whenever stability is wired, only the stable eligible branch records.
            if (policy.allow_detection_event_proposal and
                    (registered_history_eligible or stability == "NO_OBSERVATION")):
                proposals.append(ProposedAction.LOG_DETECTION_EVENT)
            if policy.allow_registered_popup_proposal:
                if registered_eligible:
                    proposals.append(ProposedAction.SHOW_REGISTERED_POPUP)
                else:
                    blocked.append(ProposedAction.SHOW_REGISTERED_POPUP)
        else:
            state = structural_state

        attendance_applicable = (
            structural_state is None
            and value.person_id is not None
            and stability == "STABLE"
            and (not policy.require_policy_eligible_for_attendance
                 or (value.policy_eligible and identification == "ELIGIBLE"))
            and (not policy.require_active_person_for_attendance
                 or value.administrative_status == "ACTIVE")
        )
        if attendance_applicable:
            if policy.allow_attendance_proposal:
                proposals.append(ProposedAction.PROPOSE_ATTENDANCE)
            else:
                blocked.append(ProposedAction.PROPOSE_ATTENDANCE)
                reasons.append("attendance_proposal_disabled")

        proposals = _action_order(proposals)
        blocked = _action_order(blocked)
        if proposals and not policy.automatic_actions_enabled and structural_state is None and state not in {
            DecisionState.BLOCKED_BY_ADMIN_STATUS, DecisionState.BLOCKED_BY_POLICY,
        }:
            state = DecisionState.ACTIONS_DISABLED
            blocked = _action_order(blocked + proposals)
            reasons.insert(0, "automatic_actions_disabled")

        return self._result(
            value, state, tuple(proposals) or (ProposedAction.NONE,), tuple(blocked),
            _ordered_unique(reasons), evaluated=True,
        )

    def _result(
        self, value: DecisionOrchestratorInput, state: DecisionState,
        proposed: tuple[ProposedAction, ...], blocked: tuple[ProposedAction, ...],
        reasons: tuple[str, ...], *, evaluated: bool,
    ) -> DecisionOrchestratorResult:
        return DecisionOrchestratorResult(
            state, evaluated, value.person_id, proposed or (ProposedAction.NONE,),
            blocked, reasons, self.policy.automatic_actions_enabled,
            self.policy.policy_name, self.policy.policy_version, value.timestamp,
        )


_ACTION_ORDER = {action: index for index, action in enumerate((
    ProposedAction.SHOW_REGISTERED_POPUP,
    ProposedAction.SHOW_UNREGISTERED_POPUP,
    ProposedAction.LOG_DETECTION_EVENT,
    ProposedAction.PROPOSE_ATTENDANCE,
))}


def _action_order(actions: list[ProposedAction]) -> list[ProposedAction]:
    return sorted(set(actions), key=_ACTION_ORDER.__getitem__)


def _ordered_unique(values: list[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(values))
