"""Classify a candidate's changes without applying them."""

from ..domain.models import ConfigurationDiffDTO
from ..domain.ports import ConfigurationPolicyPort
from ._support import diff_with_policy
from .state import ConfigurationSession


class DiffConfigurationUseCase:
    def __init__(
        self, session: ConfigurationSession, policy: ConfigurationPolicyPort
    ) -> None:
        self._session = session
        self._policy = policy

    def execute(self, candidate: dict) -> ConfigurationDiffDTO:
        return diff_with_policy(self._session, candidate, self._policy)
