"""Compatibility facade for prepare and commit restore use cases."""

from __future__ import annotations

import os
import shutil

from .application import PrepareRestoreUseCase, RestoreBackupUseCase
from .infrastructure import EngineBackupContentValidator


class RestoreService:
    def __init__(
        self,
        catalog,
        archive,
        snapshots,
        maintenance,
        *,
        disk_usage=shutil.disk_usage,
        audit_callback=None,
    ) -> None:
        self.catalog = catalog
        self.archive = archive
        self.snapshots = snapshots
        self.maintenance = maintenance
        self.disk_usage = disk_usage
        self.audit = audit_callback
        validator = EngineBackupContentValidator()
        self._prepare = PrepareRestoreUseCase(
            catalog,
            archive,
            snapshots,
            validator,
            disk_usage=disk_usage,
        )
        self._restore = RestoreBackupUseCase(
            catalog,
            maintenance,
            disk_usage=disk_usage,
            replace=lambda source, destination: os.replace(source, destination),
            audit_callback=audit_callback,
        )

    def prepare(self, archive_path):
        return self._prepare.execute(archive_path)

    def restore(self, plan, *, confirmed: bool):
        return self._restore.execute(plan, confirmed=confirmed)
