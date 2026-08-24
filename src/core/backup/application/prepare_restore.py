"""Validate and stage a backup without mutating active data."""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from ..domain.models import (
    BackupComponentType,
    BackupSpaceError,
    BackupValidationError,
    RestorePlan,
)
from ..domain.ports import (
    BackupArchivePort,
    BackupContentValidatorPort,
    BackupSourceCatalogPort,
    SQLiteSnapshotPort,
)


class PrepareRestoreUseCase:
    def __init__(
        self,
        catalog: BackupSourceCatalogPort,
        archive: BackupArchivePort,
        snapshots: SQLiteSnapshotPort,
        content_validator: BackupContentValidatorPort,
        *,
        disk_usage=shutil.disk_usage,
    ) -> None:
        self.catalog = catalog
        self.archive = archive
        self.snapshots = snapshots
        self.content_validator = content_validator
        self.disk_usage = disk_usage

    def execute(self, archive_path: Path) -> RestorePlan:
        staging = Path(tempfile.mkdtemp(prefix="fastvision-restore-"))
        try:
            if self.disk_usage(staging).free < (
                archive_path.stat().st_size * 2 + 1_048_576
            ):
                raise BackupSpaceError("insufficient space to prepare restore")
            manifest, extracted = self.archive.verify(archive_path, staging)
            for entry in manifest.files:
                self.catalog.destination_for(entry)
                path = extracted[entry.archive_path]
                if entry.component_type.value.endswith("DATABASE"):
                    if entry.schema_version is None:
                        raise BackupValidationError(
                            "SQLite schema metadata is missing"
                        )
                    if entry.schema_version > 1:
                        raise BackupValidationError(
                            "future SQLite schema is unsupported"
                        )
                    if (
                        self.snapshots.validate(path, 1)
                        != entry.schema_version
                    ):
                        raise BackupValidationError(
                            "SQLite schema metadata mismatch"
                        )
                elif (
                    entry.component_type is BackupComponentType.CONFIGURATION
                ):
                    root = json.loads(path.read_text(encoding="utf-8"))
                    if not isinstance(root, dict):
                        raise BackupValidationError(
                            "restored configuration is invalid"
                        )
            galleries = {
                entry.component_type: entry
                for entry in manifest.files
                if entry.component_type
                in {
                    BackupComponentType.GALLERY_MANIFEST,
                    BackupComponentType.GALLERY_ARCHIVE,
                }
            }
            if len(galleries) == 1:
                raise BackupValidationError(
                    "restored gallery pair is incomplete"
                )
            if len(galleries) == 2:
                self.content_validator.validate_gallery(
                    extracted[
                        galleries[
                            BackupComponentType.GALLERY_MANIFEST
                        ].archive_path
                    ],
                    extracted[
                        galleries[
                            BackupComponentType.GALLERY_ARCHIVE
                        ].archive_path
                    ],
                )
            return RestorePlan(
                manifest.backup_id,
                archive_path,
                staging,
                manifest.files,
                sum(entry.size for entry in manifest.files),
                True,
            )
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
