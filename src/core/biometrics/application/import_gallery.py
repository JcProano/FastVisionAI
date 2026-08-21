"""Use case for transactionally importing a validated biometric gallery."""

from pathlib import Path

from ..domain.ports import BiometricGalleryPort, GalleryPersistencePort


class ImportGalleryUseCase:
    def __init__(self, persistence: GalleryPersistencePort) -> None:
        self._persistence = persistence

    def execute(
        self,
        gallery: BiometricGalleryPort,
        manifest_path: Path,
        archive_path: Path,
    ) -> None:
        self._persistence.import_into(gallery, manifest_path, archive_path)
