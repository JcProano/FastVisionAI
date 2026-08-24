"""Reload a validated snapshot without reconstructing runtime services."""

from pathlib import Path

from ..domain.models import ConfigurationOperationResult, ConfigurationProfile
from ..domain.ports import ConfigurationLoaderPort, ConfigurationPolicyPort
from ._support import audit_safely, diff_with_policy
from .state import ConfigurationSession


class ReloadConfigurationUseCase:
    def __init__(
        self,
        session: ConfigurationSession,
        loader: ConfigurationLoaderPort,
        policy: ConfigurationPolicyPort,
        path: Path,
        profile: ConfigurationProfile,
        audit_callback=None,
    ) -> None:
        self._session = session
        self._loader = loader
        self._policy = policy
        self._path = path
        self._profile = profile
        self._audit = audit_callback

    def execute(self) -> ConfigurationOperationResult:
        loaded = self._loader.load(self._path, self._profile)
        difference = diff_with_policy(
            self._session, loaded.as_mapping(), self._policy
        )
        self._session.replace(
            loaded,
            restart_required=bool(
                difference.restart_required or difference.immutable
            ),
        )
        audit_safely(self._audit, "CONFIG_RELOADED", self._profile)
        return ConfigurationOperationResult(
            True,
            "Snapshot recargado; los servicios no fueron reconstruidos.",
            diff=difference,
        )
