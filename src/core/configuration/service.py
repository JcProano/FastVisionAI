"""Compatibility facade composing explicit configuration use cases."""

from __future__ import annotations

import os
from pathlib import Path

from src.version import __version__

from .application import (
    ConfigurationSession,
    DiffConfigurationUseCase,
    ExportConfigurationUseCase,
    GetConfigurationUseCase,
    ImportConfigurationUseCase,
    ReloadConfigurationUseCase,
    SaveConfigurationUseCase,
    ValidateConfigurationUseCase,
)
from .domain.models import ConfigurationProfile
from .infrastructure import (
    AtomicConfigurationStore,
    ProjectConfigurationPolicy,
)


class ConfigurationService:
    def __init__(
        self,
        loader,
        path: Path,
        profile: ConfigurationProfile,
        *,
        backup_count=10,
        audit_callback=None,
        application_version=__version__,
    ) -> None:
        if backup_count <= 0:
            raise ValueError("backup_count must be positive")
        self.loader = loader
        self.path = path
        self.profile = profile
        self.backup_count = backup_count
        self.audit = audit_callback
        self.application_version = application_version
        self._session = ConfigurationSession(loader.load(path, profile))
        self._policy = ProjectConfigurationPolicy(loader.validator)
        self._store = AtomicConfigurationStore(
            loader,
            path,
            profile,
            replace=lambda source, destination: os.replace(source, destination),
            rotate=lambda directory: self._rotate(directory),
            fsync_directory=lambda directory: self._fsync_directory(directory),
        )
        self._get = GetConfigurationUseCase(self._session)
        self._validate = ValidateConfigurationUseCase(
            self._policy, profile, audit_callback
        )
        self._diff = DiffConfigurationUseCase(self._session, self._policy)
        self._reload = ReloadConfigurationUseCase(
            self._session,
            loader,
            self._policy,
            path,
            profile,
            audit_callback,
        )
        self._save = SaveConfigurationUseCase(
            self._session,
            self._policy,
            self._store,
            profile,
            audit_callback,
        )
        self._import = ImportConfigurationUseCase(
            self._session,
            loader,
            self._policy,
            profile,
            audit_callback,
        )
        self._export = ExportConfigurationUseCase(
            self._session,
            self._policy,
            self._store,
            application_version=application_version,
        )

    @property
    def restart_required_pending(self) -> bool:
        return self._session.restart_required_pending

    def current(self):
        return self._get.execute()

    def validate_candidate(self, candidate):
        return self._validate.execute(candidate)

    def diff(self, candidate):
        return self._diff.execute(candidate)

    def reload(self):
        return self._reload.execute()

    def save(self, candidate):
        return self._save.execute(candidate)

    def import_candidate(self, path: Path):
        return self._import.execute(path)

    def export(self, path: Path, *, overwrite=False):
        return self._export.execute(path, overwrite=overwrite)

    def _rotate(self, directory: Path) -> None:
        items = sorted(
            directory.glob(f"{self.path.stem}.*.json"),
            key=lambda item: item.name,
            reverse=True,
        )
        for item in items[self.backup_count :]:
            item.unlink()

    @staticmethod
    def _fsync_directory(directory: Path) -> None:
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
