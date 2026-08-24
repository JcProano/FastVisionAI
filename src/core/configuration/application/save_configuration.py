"""Validate and atomically persist a configuration candidate."""

from ..domain.models import ConfigurationOperationResult, ConfigurationProfile
from ..domain.ports import ConfigurationPolicyPort, ConfigurationStorePort
from ._support import audit_safely, diff_with_policy
from .state import ConfigurationSession


class SaveConfigurationUseCase:
    def __init__(
        self,
        session: ConfigurationSession,
        policy: ConfigurationPolicyPort,
        store: ConfigurationStorePort,
        profile: ConfigurationProfile,
        audit_callback=None,
    ) -> None:
        self._session = session
        self._policy = policy
        self._store = store
        self._profile = profile
        self._audit = audit_callback

    def execute(self, candidate: dict) -> ConfigurationOperationResult:
        validation = self._policy.validate(candidate, self._profile)
        if not validation.valid:
            return ConfigurationOperationResult(
                False, "Configuración inválida; no se guardó.", validation
            )
        normalized = self._policy.normalize(candidate)
        difference = diff_with_policy(
            self._session, normalized, self._policy
        )
        try:
            loaded, warning = self._store.save(normalized)
        except Exception:
            return ConfigurationOperationResult(
                False,
                "No se pudo guardar; el archivo original permanece disponible.",
                validation,
                difference,
            )
        self._session.replace(
            loaded,
            restart_required=bool(
                difference.restart_required or difference.immutable
            ),
        )
        audit_safely(self._audit, "CONFIG_SAVED", self._profile)
        return ConfigurationOperationResult(
            True,
            "Configuración guardada; los cambios no se aplicaron automáticamente.",
            validation,
            difference,
            warning,
        )
