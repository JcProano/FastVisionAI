"""Dependency-inversion ports for backup and restore workflows."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Protocol

from .models import (
    BackupFileEntry,
    BackupManifest,
    BackupRequest,
    MaintenanceState,
)


class BackupSourcePort(Protocol):
    logical_path: str
    source_path: Path
    archive_path: str
    component_type: object
    is_sqlite: bool


class BackupSourceCatalogPort(Protocol):
    root: Path
    def sources(self) -> tuple[BackupSourcePort, ...]: ...
    def thumbnail_directory(self) -> Path: ...
    def destination_for(self, entry: BackupFileEntry) -> Path: ...


class DiskUsagePort(Protocol):
    free: int


class BackupArchivePort(Protocol):
    def disk_usage(self, path: Path) -> DiskUsagePort: ...
    def create(
        self,
        destination: Path,
        manifest: BackupManifest,
        files: dict[str, Path],
        *,
        overwrite: bool = False,
    ) -> None: ...
    def verify(
        self, archive_path: Path, extract_to: Path | None = None
    ) -> tuple[BackupManifest, dict[str, Path]]: ...


class SQLiteSnapshotPort(Protocol):
    def create(self, source: Path, destination: Path) -> tuple[int, datetime]: ...
    def validate(self, path: Path, supported_version: int) -> int: ...


class MaintenancePort(Protocol):
    @property
    def state(self) -> MaintenanceState: ...
    def begin_backup(self) -> None: ...
    def end_backup(self) -> None: ...
    def begin_restore(self) -> None: ...
    def complete_restore(self) -> None: ...
    def fail(self) -> None: ...


class BackupContentValidatorPort(Protocol):
    def validate_gallery(self, manifest_path: Path, archive_path: Path) -> None: ...
    def validate_thumbnail(self, path: Path) -> None: ...
