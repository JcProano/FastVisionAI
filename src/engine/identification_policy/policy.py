"""Explicit policy configuration without production biometric thresholds."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .contracts import IdentificationPolicyValidationError


@dataclass(frozen=True, slots=True)
class IdentificationPolicy:
    enabled: bool = True
    automatic_actions_enabled: bool = False
    require_candidate: bool = True
    require_active_person: bool = True
    require_stable_observation: bool = True
    minimum_quality_score: float | None = None
    minimum_similarity: float | None = None
    minimum_stability_observations: int | None = None
    minimum_stability_duration_seconds: float | None = None
    reject_incompatible: bool = True
    reject_ambiguous: bool = True
    policy_name: str = "identification_policy_development"
    policy_version: str = "1.0"

    def __post_init__(self) -> None:
        if self.minimum_quality_score is not None and not _bounded(
            self.minimum_quality_score, 0.0, 100.0,
        ):
            raise IdentificationPolicyValidationError(
                "minimum_quality_score must be within [0, 100]"
            )
        if self.minimum_similarity is not None and not _bounded(
            self.minimum_similarity, -1.0, 1.0,
        ):
            raise IdentificationPolicyValidationError(
                "minimum_similarity must be within [-1, 1]"
            )
        if (
            self.minimum_stability_observations is not None
            and self.minimum_stability_observations <= 0
        ):
            raise IdentificationPolicyValidationError(
                "minimum_stability_observations must be positive"
            )
        if (
            self.minimum_stability_duration_seconds is not None
            and (
                not math.isfinite(self.minimum_stability_duration_seconds)
                or self.minimum_stability_duration_seconds < 0
            )
        ):
            raise IdentificationPolicyValidationError(
                "minimum_stability_duration_seconds must be non-negative"
            )
        if not self.policy_name.strip() or not self.policy_version.strip():
            raise IdentificationPolicyValidationError("policy provenance is required")


def _bounded(value: float, minimum: float, maximum: float) -> bool:
    return math.isfinite(value) and minimum <= value <= maximum
