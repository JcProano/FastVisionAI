"""Adapter over the project's allowlist and redaction validators."""

from __future__ import annotations

from typing import Any

from ..domain.models import ConfigurationProfile, ConfigurationValidationResult
from ..validators import known_only, redact


class ProjectConfigurationPolicy:
    def __init__(self, validator) -> None:
        self.validator = validator

    def validate(
        self, candidate: object, profile: ConfigurationProfile
    ) -> ConfigurationValidationResult:
        return self.validator.validate(candidate, profile)

    def normalize(self, candidate: dict[str, Any]) -> dict[str, Any]:
        return known_only(candidate)

    def redact(self, value: Any, key: str = "") -> Any:
        return redact(value, key)
