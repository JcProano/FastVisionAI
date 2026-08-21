"""OpenCV and biometric-gallery validation adapter for backup content."""

from pathlib import Path

import cv2
import numpy as np

from src.core.biometrics.application import ImportGalleryUseCase
from src.core.biometrics.infrastructure import GalleryPersistence
from src.engine.gallery import FaceGallery

from ..domain.models import BackupValidationError


class EngineBackupContentValidator:
    def __init__(self) -> None:
        self._import_gallery = ImportGalleryUseCase(
            GalleryPersistence(enabled=True)
        )

    def validate_gallery(self, manifest_path: Path, archive_path: Path) -> None:
        self._import_gallery.execute(FaceGallery(), manifest_path, archive_path)

    def validate_thumbnail(self, path: Path) -> None:
        image = cv2.imdecode(
            np.frombuffer(path.read_bytes(), np.uint8), cv2.IMREAD_COLOR
        )
        if image is None:
            raise BackupValidationError("thumbnail image is invalid")
