"""Composition container for the validated configuration lifecycle."""

from pathlib import Path

from .domain.models import ConfigurationProfile
from .infrastructure import JSONConfigurationLoader
from .service import ConfigurationService
from .validators import ConfigurationValidator


class ConfigurationContainer:
    @staticmethod
    def build_service(
        path: Path,
        manager_settings: dict[str, object],
        project_root: Path,
        *,
        loader_type=JSONConfigurationLoader,
        validator_type=ConfigurationValidator,
        service_type=ConfigurationService,
    ) -> ConfigurationService:
        try:
            profile = ConfigurationProfile(
                str(manager_settings.get("profile", "DEVELOPMENT"))
            )
        except ValueError as exc:
            raise ValueError("configuration profile is unavailable") from exc
        if profile not in {
            ConfigurationProfile.DEVELOPMENT,
            ConfigurationProfile.PRODUCTION,
        }:
            raise ValueError("configuration profile is unavailable")
        loader = loader_type(validator_type(project_root))
        return service_type(
            loader,
            path,
            profile,
            backup_count=int(manager_settings.get("backup_count", 10)),
        )
