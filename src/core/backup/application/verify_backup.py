"""Verify archive integrity and application compatibility."""

from pathlib import Path

from ..domain.models import (
    BackupValidationError,
    BackupVerificationResult,
)
from ..domain.ports import BackupArchivePort
from ._audit import audit_safely


class VerifyBackupUseCase:
    def __init__(self, archive: BackupArchivePort, audit_callback=None) -> None:
        self.archive = archive
        self.audit = audit_callback

    def execute(self, path: Path) -> BackupVerificationResult:
        try:
            manifest, _ = self.archive.verify(path)
            for item in manifest.files:
                if item.component_type.value.endswith("DATABASE") and (
                    item.schema_version is None or item.schema_version > 1
                ):
                    raise BackupValidationError("SQLite schema is unsupported")
            audit_safely(self.audit, "VERIFY_SUCCESS")
            return BackupVerificationResult(
                True,
                manifest.backup_id,
                len(manifest.files),
                path.stat().st_size,
                "Backup válido. El backup contiene información sensible y no está cifrado.",
            )
        except Exception:
            audit_safely(self.audit, "VERIFY_FAILED")
            raise
