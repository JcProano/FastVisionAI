"""Load a candidate file for review without applying it."""

from pathlib import Path

from ..domain.models import ConfigurationDiffDTO, ConfigurationProfile
from ..domain.ports import ConfigurationLoaderPort, ConfigurationPolicyPort
from ._support import audit_safely, diff_with_policy
from .state import ConfigurationSession


class ImportConfigurationUseCase:
    def __init__(
        self,
        session: ConfigurationSession,
        loader: ConfigurationLoaderPort,
        policy: ConfigurationPolicyPort,
        profile: ConfigurationProfile,
        audit_callback=None,
    ) -> None:
        self._session = session
        self._loader = loader
        self._policy = policy
        self._profile = profile
        self._audit = audit_callback

    def execute(self, path: Path) -> tuple[dict, ConfigurationDiffDTO]:
        try:
            candidate = self._loader.load(path, self._profile).as_mapping()
            return candidate, diff_with_policy(
                self._session, candidate, self._policy
            )
        except Exception:
            audit_safely(
                self._audit, "CONFIG_IMPORT_REJECTED", self._profile
            )
            raise
