"""Validate a candidate without mutating current configuration."""

from ..domain.models import ConfigurationProfile, ConfigurationValidationResult
from ..domain.ports import ConfigurationPolicyPort
from ._support import audit_safely


class ValidateConfigurationUseCase:
    def __init__(
        self,
        policy: ConfigurationPolicyPort,
        profile: ConfigurationProfile,
        audit_callback=None,
    ) -> None:
        self._policy = policy
        self._profile = profile
        self._audit = audit_callback

    def execute(self, candidate: object) -> ConfigurationValidationResult:
        result = self._policy.validate(candidate, self._profile)
        audit_safely(self._audit, "CONFIG_VALIDATED", self._profile)
        return result
