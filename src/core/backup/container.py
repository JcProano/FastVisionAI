"""Composition container for backup and restore adapters."""

from dataclasses import dataclass
from pathlib import Path

from .archive import BackupArchive
from .catalog import BackupSourceCatalog
from .maintenance import ApplicationMaintenanceCoordinator
from .restore import RestoreService
from .service import BackupService
from .sqlite_snapshot import SQLiteSnapshotProvider


@dataclass(frozen=True, slots=True)
class BackupComponents:
    maintenance: object
    catalog: object
    archive: object
    snapshots: object
    backup_service: object
    restore_service: object


class BackupContainer:
    @staticmethod
    def build(
        settings: dict[str, object],
        project_root: Path,
        *,
        backup_audit_callback=None,
        restore_audit_callback=None,
        maintenance_type=ApplicationMaintenanceCoordinator,
        catalog_type=BackupSourceCatalog,
        archive_type=BackupArchive,
        snapshot_type=SQLiteSnapshotProvider,
        backup_service_type=BackupService,
        restore_service_type=RestoreService,
    ) -> BackupComponents:
        configuration = settings.get("backup", {})
        if not isinstance(configuration, dict):
            raise ValueError("backup configuration must be an object")
        for key in (
            "maximum_archive_size_bytes",
            "maximum_file_count",
            "operation_history_limit",
        ):
            if int(configuration.get(key, 0)) <= 0:
                raise ValueError(f"backup {key} must be positive")
        for key in (
            "restore_timeout_seconds",
            "sqlite_snapshot_timeout_seconds",
        ):
            if float(configuration.get(key, 0)) <= 0:
                raise ValueError(f"backup {key} must be positive")
        maintenance = maintenance_type()
        catalog = catalog_type(project_root, settings)
        archive = archive_type(
            maximum_archive_size_bytes=int(
                configuration["maximum_archive_size_bytes"]
            ),
            maximum_file_count=int(configuration["maximum_file_count"]),
        )
        snapshots = snapshot_type(
            float(configuration["sqlite_snapshot_timeout_seconds"])
        )
        backup_service = backup_service_type(
            catalog,
            archive,
            snapshots,
            maintenance,
            audit_callback=backup_audit_callback,
        )
        restore_service = restore_service_type(
            catalog,
            archive,
            snapshots,
            maintenance,
            audit_callback=restore_audit_callback,
        )
        return BackupComponents(
            maintenance,
            catalog,
            archive,
            snapshots,
            backup_service,
            restore_service,
        )
