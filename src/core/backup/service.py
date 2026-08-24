"""Compatibility facade for create and verify backup use cases."""

from src.version import __version__

from .application import CreateBackupUseCase, VerifyBackupUseCase
from .infrastructure import EngineBackupContentValidator


class BackupService:
    def __init__(
        self,
        catalog,
        archive,
        snapshots,
        maintenance=None,
        *,
        application_version: str = __version__,
        audit_callback=None,
    ) -> None:
        self.catalog = catalog
        self.archive = archive
        self.snapshots = snapshots
        self.maintenance = maintenance
        self.application_version = application_version
        self.audit = audit_callback
        validator = EngineBackupContentValidator()
        self._create = CreateBackupUseCase(
            catalog,
            archive,
            snapshots,
            validator,
            maintenance,
            application_version=application_version,
            audit_callback=audit_callback,
        )
        self._verify = VerifyBackupUseCase(archive, audit_callback)

    def create(self, request):
        return self._create.execute(request)

    def verify(self, path):
        return self._verify.execute(path)
