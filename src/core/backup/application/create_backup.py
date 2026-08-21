"""Create one internally consistent backup package."""

from __future__ import annotations

import json
import shutil
import tempfile
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from ..domain.models import (
    BACKUP_FORMAT_VERSION,
    BackupComponentType,
    BackupFileEntry,
    BackupManifest,
    BackupRequest,
    BackupResult,
    BackupSpaceError,
    BackupValidationError,
)
from ..domain.ports import (
    BackupArchivePort,
    BackupContentValidatorPort,
    BackupSourceCatalogPort,
    MaintenancePort,
    SQLiteSnapshotPort,
)
from ._audit import audit_safely


class CreateBackupUseCase:
    def __init__(
        self,
        catalog: BackupSourceCatalogPort,
        archive: BackupArchivePort,
        snapshots: SQLiteSnapshotPort,
        content_validator: BackupContentValidatorPort,
        maintenance: MaintenancePort | None = None,
        *,
        application_version: str,
        audit_callback=None,
        new_id: Callable[[], str] = lambda: str(uuid.uuid4()),
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.catalog = catalog
        self.archive = archive
        self.snapshots = snapshots
        self.content_validator = content_validator
        self.maintenance = maintenance
        self.application_version = application_version
        self.audit = audit_callback
        self._new_id = new_id
        self._now = now

    def execute(self, request: BackupRequest) -> BackupResult:
        audit_safely(self.audit, "BACKUP_STARTED")
        backup_id = self._new_id()
        if self.maintenance:
            self.maintenance.begin_backup()
        try:
            sources = self.catalog.sources()
            estimated = sum(
                source.source_path.stat().st_size
                for source in sources
                if source.source_path.is_file()
            )
            thumbnail_directory = self.catalog.thumbnail_directory()
            if thumbnail_directory.is_dir():
                estimated += sum(
                    path.stat().st_size
                    for path in thumbnail_directory.iterdir()
                    if path.is_file() and not path.is_symlink()
                )
            if self.archive.disk_usage(Path(tempfile.gettempdir())).free < (
                estimated + 1_048_576
            ):
                raise BackupSpaceError(
                    "insufficient temporary space to create backup"
                )
            with tempfile.TemporaryDirectory(
                prefix="fastvision-backup-"
            ) as name:
                staging = Path(name)
                files: dict[str, Path] = {}
                entries: list[BackupFileEntry] = []
                missing: list[str] = []
                gallery = [
                    source
                    for source in sources
                    if source.component_type
                    in {
                        BackupComponentType.GALLERY_MANIFEST,
                        BackupComponentType.GALLERY_ARCHIVE,
                    }
                ]
                if sum(source.source_path.exists() for source in gallery) == 1:
                    raise BackupValidationError(
                        "gallery persistence pair is incomplete"
                    )
                if gallery and all(
                    source.source_path.is_file() for source in gallery
                ):
                    by_type = {
                        source.component_type: source.source_path
                        for source in gallery
                    }
                    self.content_validator.validate_gallery(
                        by_type[BackupComponentType.GALLERY_MANIFEST],
                        by_type[BackupComponentType.GALLERY_ARCHIVE],
                    )
                for source in sources:
                    if not source.source_path.is_file():
                        missing.append(source.component_type.value)
                        continue
                    if source.source_path.is_symlink():
                        raise BackupValidationError(
                            "backup source symlink is forbidden"
                        )
                    target = staging / source.archive_path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    schema_version = None
                    snapshot_at = None
                    if source.is_sqlite:
                        schema_version, snapshot_at = self.snapshots.create(
                            source.source_path, target
                        )
                    else:
                        if (
                            source.component_type
                            is BackupComponentType.CONFIGURATION
                        ):
                            json.loads(
                                source.source_path.read_text(encoding="utf-8")
                            )
                        shutil.copyfile(source.source_path, target)
                    entry = BackupFileEntry(
                        source.logical_path,
                        source.archive_path,
                        source.component_type,
                        target.stat().st_size,
                        _sha256_file(target),
                        schema_version,
                        snapshot_at,
                    )
                    entries.append(entry)
                    files[source.archive_path] = target
                self._stage_thumbnails(staging, entries, files)
                staged_gallery = {
                    entry.component_type: files[entry.archive_path]
                    for entry in entries
                    if entry.component_type
                    in {
                        BackupComponentType.GALLERY_MANIFEST,
                        BackupComponentType.GALLERY_ARCHIVE,
                    }
                }
                if len(staged_gallery) == 2:
                    self.content_validator.validate_gallery(
                        staged_gallery[BackupComponentType.GALLERY_MANIFEST],
                        staged_gallery[BackupComponentType.GALLERY_ARCHIVE],
                    )
                manifest = BackupManifest(
                    BACKUP_FORMAT_VERSION,
                    self._now(),
                    "FastVisionAI",
                    self.application_version,
                    backup_id,
                    "NONE",
                    tuple(sorted(entries, key=lambda item: item.archive_path)),
                    tuple(sorted(set(missing))),
                )
                self.archive.create(
                    request.destination,
                    manifest,
                    files,
                    overwrite=request.overwrite,
                )
            result = BackupResult(
                True,
                backup_id,
                request.destination.name,
                len(entries),
                request.destination.stat().st_size,
                manifest.missing_components,
                "Backup creado. El backup contiene información sensible y no está cifrado.",
            )
            audit_safely(self.audit, "BACKUP_SUCCESS")
            return result
        except Exception:
            audit_safely(self.audit, "BACKUP_FAILED")
            raise
        finally:
            if self.maintenance:
                self.maintenance.end_backup()

    def _stage_thumbnails(
        self,
        staging: Path,
        entries: list[BackupFileEntry],
        files: dict[str, Path],
    ) -> None:
        directory = self.catalog.thumbnail_directory()
        if not directory.exists():
            return
        if directory.is_symlink():
            raise BackupValidationError(
                "thumbnail directory symlink is forbidden"
            )
        for path in sorted(directory.iterdir(), key=lambda item: item.name):
            if path.is_symlink():
                raise BackupValidationError("thumbnail symlink is forbidden")
            if (
                not path.is_file()
                or path.suffix.casefold() not in {".jpg", ".jpeg", ".png"}
                or path.name.startswith(".")
            ):
                continue
            if not path.stem or not all(
                character.isalnum() or character in "_-"
                for character in path.stem
            ):
                raise BackupValidationError("thumbnail filename is invalid")
            self.content_validator.validate_thumbnail(path)
            archive_path = f"components/thumbnails/{path.name}"
            target = staging / archive_path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            entries.append(
                BackupFileEntry(
                    str(path.relative_to(self.catalog.root)),
                    archive_path,
                    BackupComponentType.THUMBNAIL,
                    target.stat().st_size,
                    _sha256_file(target),
                )
            )
            files[archive_path] = target


def _sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
