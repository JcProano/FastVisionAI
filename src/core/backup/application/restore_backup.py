"""Commit a staged restore with verified compensation on failure."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from ..domain.models import (
    BackupSpaceError,
    MaintenanceState,
    RestoreError,
    RestorePlan,
    RestoreResult,
    RestoreRollbackError,
)
from ..domain.ports import BackupSourceCatalogPort, MaintenancePort
from ._audit import audit_safely


class RestoreBackupUseCase:
    def __init__(
        self,
        catalog: BackupSourceCatalogPort,
        maintenance: MaintenancePort,
        *,
        disk_usage=shutil.disk_usage,
        replace,
        audit_callback=None,
    ) -> None:
        self.catalog = catalog
        self.maintenance = maintenance
        self.disk_usage = disk_usage
        self._replace = replace
        self.audit = audit_callback

    def execute(self, plan: RestorePlan, *, confirmed: bool) -> RestoreResult:
        if not confirmed:
            return RestoreResult(
                False,
                plan.backup_id,
                0,
                False,
                False,
                "Restauración cancelada.",
            )
        audit_safely(self.audit, "RESTORE_STARTED")
        rollback = Path(
            tempfile.mkdtemp(prefix="fastvision-rollback-", dir=self.catalog.root)
        )
        moved: list[tuple[Path, Path, str]] = []
        installed: list[Path] = []
        try:
            if self.maintenance.state is not MaintenanceState.QUIESCENT:
                raise RestoreError("restore requires application quiescence")
            if self.disk_usage(self.catalog.root).free < (
                plan.total_size * 2 + 1_048_576
            ):
                raise BackupSpaceError("insufficient space to commit restore")
            self.maintenance.begin_restore()
            for entry in plan.files:
                source = plan.staging_directory / entry.archive_path
                destination = self.catalog.destination_for(entry)
                destination.parent.mkdir(parents=True, exist_ok=True)
                previous = rollback / entry.logical_path
                previous.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists():
                    self._replace(destination, previous)
                    moved.append(
                        (previous, destination, _sha256_file(previous))
                    )
                self._replace(source, destination)
                installed.append(destination)
            self.maintenance.complete_restore()
            shutil.rmtree(rollback, ignore_errors=True)
            shutil.rmtree(plan.staging_directory, ignore_errors=True)
            audit_safely(self.audit, "RESTORE_SUCCESS")
            return RestoreResult(
                True,
                plan.backup_id,
                len(installed),
                False,
                True,
                "Restauración completada; reinicio y nuevo login obligatorios.",
            )
        except Exception as original:
            rollback_ok = True
            for destination in reversed(installed):
                try:
                    destination.unlink(missing_ok=True)
                except Exception:
                    rollback_ok = False
            for previous, destination, digest in reversed(moved):
                try:
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    self._replace(previous, destination)
                    if _sha256_file(destination) != digest:
                        rollback_ok = False
                except Exception:
                    rollback_ok = False
            shutil.rmtree(plan.staging_directory, ignore_errors=True)
            audit_safely(self.audit, "RESTORE_FAILED")
            if not rollback_ok:
                self.maintenance.fail()
                raise RestoreRollbackError(
                    "restore rollback could not be verified; manual recovery is required"
                ) from original
            shutil.rmtree(rollback, ignore_errors=True)
            self.maintenance.fail()
            raise RestoreError(
                "restore failed and original files were restored"
            ) from original


def _sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
