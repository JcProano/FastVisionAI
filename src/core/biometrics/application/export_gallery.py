"""Use case for explicitly exporting an encrypted-or-development gallery adapter."""

from pathlib import Path

from ..domain.ports import BiometricGalleryPort, GalleryPersistencePort


class ExportGalleryUseCase:
    def __init__(self, persistence: GalleryPersistencePort) -> None:
        self._persistence = persistence

    def execute(
        self,
        gallery: BiometricGalleryPort,
        manifest_path: Path,
        archive_path: Path,
        *,
        overwrite: bool = False,
    ) -> None:
        self._persistence.export(
            gallery,
            manifest_path,
            archive_path,
            overwrite=overwrite,
        )
