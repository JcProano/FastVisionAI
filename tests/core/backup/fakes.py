"""Test doubles for backup and restore application ports."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.core.backup.domain import BackupManifest, MaintenanceState


@dataclass(frozen=True)
class FakeUsage:
    free: int = 10**12


class FakeCatalog:
    def __init__(self, root: Path) -> None:
        self.root = root

    def sources(self) -> tuple:
        return ()

    def thumbnail_directory(self) -> Path:
        return self.root / "missing-thumbnails"

    def destination_for(self, entry) -> Path:
        return self.root / entry.logical_path


class FakeArchive:
    def __init__(self, manifest: BackupManifest | None = None) -> None:
        self.manifest = manifest
        self.created_manifest = None

    def disk_usage(self, path: Path) -> FakeUsage:
        del path
        return FakeUsage()

    def create(
        self, destination, manifest, files, *, overwrite=False
    ) -> None:
        del files, overwrite
        self.created_manifest = manifest
        destination.write_bytes(b"backup")

    def verify(self, archive_path, extract_to=None):
        del archive_path, extract_to
        assert self.manifest is not None
        return self.manifest, {}


class FakeSnapshots:
    def validate(self, path, supported_version):
        del path
        return supported_version


class FakeContentValidator:
    def validate_gallery(self, manifest_path, archive_path):
        del manifest_path, archive_path

    def validate_thumbnail(self, path):
        del path


class FakeMaintenance:
    def __init__(self) -> None:
        self.state = MaintenanceState.QUIESCENT
        self.events: list[str] = []

    def begin_backup(self):
        self.events.append("begin_backup")

    def end_backup(self):
        self.events.append("end_backup")

    def begin_restore(self):
        self.events.append("begin_restore")

    def complete_restore(self):
        self.events.append("complete_restore")

    def fail(self):
        self.state = MaintenanceState.FAILED
        self.events.append("fail")
