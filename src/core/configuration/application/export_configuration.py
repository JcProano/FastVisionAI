"""Export a redacted configuration snapshot."""

from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from ..domain.models import ConfigurationOperationResult
from ..domain.ports import ConfigurationPolicyPort, ConfigurationStorePort
from .state import ConfigurationSession


class ExportConfigurationUseCase:
    def __init__(
        self,
        session: ConfigurationSession,
        policy: ConfigurationPolicyPort,
        store: ConfigurationStorePort,
        *,
        application_version: str,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._session = session
        self._policy = policy
        self._store = store
        self._application_version = application_version
        self._now = now

    def execute(
        self, path: Path, *, overwrite: bool = False
    ) -> ConfigurationOperationResult:
        value = self._policy.redact(self._session.current().as_mapping())
        value["exported_at"] = self._now().isoformat()
        value["exported_by_version"] = self._application_version
        self._store.export(value, path, overwrite=overwrite)
        return ConfigurationOperationResult(
            True, "Configuración exportada sin secretos."
        )
