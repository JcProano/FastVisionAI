"""Pure, stateless and thread-safe identification policy evaluation."""

from __future__ import annotations

from .contracts import (
    IdentificationPolicyInput, IdentificationPolicyResult, IdentificationPolicyState,
)
from .policy import IdentificationPolicy


class IdentificationPolicyEngine:
    """Evaluate safe scalar signals without actions or mutable state."""

    __slots__ = ("policy",)

    def __init__(self, policy: IdentificationPolicy | None = None) -> None:
        self.policy = policy or IdentificationPolicy()

    def evaluate(self, value: IdentificationPolicyInput) -> IdentificationPolicyResult:
        policy = self.policy
        if not policy.enabled:
            return self._result(
                value, IdentificationPolicyState.POLICY_NOT_EVALUATED,
                False, ("policy_disabled",),
            )

        failures: list[tuple[IdentificationPolicyState, str]] = []
        recognition = value.recognition_state.upper()
        stability = value.stability_state.upper()

        if value.face_count == 0:
            failures.append((IdentificationPolicyState.NO_CANDIDATE, "no_candidate"))
        elif value.face_count > 1:
            failures.append((IdentificationPolicyState.AMBIGUOUS, "multiple_faces"))
        if recognition == "INCOMPATIBLE" and policy.reject_incompatible:
            failures.append((
                IdentificationPolicyState.INCOMPATIBLE, "recognition_incompatible",
            ))
        elif recognition == "AMBIGUOUS" and policy.reject_ambiguous:
            failures.append((IdentificationPolicyState.AMBIGUOUS, "recognition_ambiguous"))
        elif recognition not in {
            "NOT_EVALUATED", "NO_GALLERY", "MATCH", "UNKNOWN", "AMBIGUOUS",
            "INCOMPATIBLE",
        }:
            failures.append((
                IdentificationPolicyState.REJECTED_BY_POLICY,
                "recognition_state_unsupported",
            ))
        if policy.require_candidate and value.person_id is None:
            failures.append((IdentificationPolicyState.NO_CANDIDATE, "no_candidate"))
        if policy.require_active_person and value.administrative_status != "ACTIVE":
            failures.append((
                IdentificationPolicyState.PERSON_NOT_ACTIVE, "person_not_active",
            ))
        if policy.require_stable_observation and stability != "STABLE":
            failures.append((
                IdentificationPolicyState.INSUFFICIENT_STABILITY,
                "observation_not_stable",
            ))
        if stability not in {
            "NO_OBSERVATION", "STABILIZING", "STABLE", "LOST", "CHANGED",
            "MULTIPLE_FACES", "INCOMPATIBLE",
        }:
            failures.append((
                IdentificationPolicyState.INSUFFICIENT_STABILITY,
                "stability_state_unsupported",
            ))
        if (
            policy.minimum_stability_observations is not None
            and value.stability_observations < policy.minimum_stability_observations
        ):
            failures.append((
                IdentificationPolicyState.INSUFFICIENT_STABILITY,
                "stability_observations_insufficient",
            ))
        if (
            policy.minimum_stability_duration_seconds is not None
            and value.stability_duration_seconds
            < policy.minimum_stability_duration_seconds
        ):
            failures.append((
                IdentificationPolicyState.INSUFFICIENT_STABILITY,
                "stability_duration_insufficient",
            ))
        if policy.minimum_quality_score is not None:
            if (
                value.quality_score is None
                or value.quality_score < policy.minimum_quality_score
            ):
                failures.append((
                    IdentificationPolicyState.INSUFFICIENT_QUALITY,
                    "quality_unavailable" if value.quality_score is None
                    else "quality_below_policy_minimum",
                ))
        if policy.minimum_similarity is not None:
            if (
                value.similarity is None or value.similarity < policy.minimum_similarity
            ):
                failures.append((
                    IdentificationPolicyState.REJECTED_BY_POLICY,
                    "similarity_unavailable" if value.similarity is None
                    else "similarity_below_policy_minimum",
                ))

        ordered = _ordered_unique(failures)
        if not ordered:
            return self._result(value, IdentificationPolicyState.ELIGIBLE, True, ())
        return self._result(value, ordered[0][0], False, tuple(item[1] for item in ordered))

    def _result(
        self, value: IdentificationPolicyInput, state: IdentificationPolicyState,
        eligible: bool, reasons: tuple[str, ...],
    ) -> IdentificationPolicyResult:
        return IdentificationPolicyResult(
            state, state is not IdentificationPolicyState.POLICY_NOT_EVALUATED,
            eligible, value.person_id, reasons, value.similarity, value.quality_score,
            value.stability_state, value.administrative_status,
            self.policy.policy_name, self.policy.policy_version, value.timestamp,
        )


def _ordered_unique(
    failures: list[tuple[IdentificationPolicyState, str]],
) -> tuple[tuple[IdentificationPolicyState, str], ...]:
    unique: dict[str, tuple[IdentificationPolicyState, str]] = {}
    for item in failures:
        unique.setdefault(item[1], item)
    return tuple(unique.values())
