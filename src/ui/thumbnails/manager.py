"""Independent filesystem manager for visual-only face thumbnails."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Sequence

import cv2
import numpy as np

from src.engine.capture_quality import CapturePose

from .contracts import ThumbnailDTO, ThumbnailSample

SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")


class ThumbnailError(RuntimeError):
    pass


class ThumbnailExistsError(ThumbnailError):
    pass


class ThumbnailManager:
    def __init__(
        self, project_root: Path, directory: Path, *, enabled: bool = True,
        width: int = 224, height: int = 224, image_format: str = "jpeg",
        jpeg_quality: int = 90, replace_existing: bool = False,
    ) -> None:
        if width <= 0 or height <= 0:
            raise ValueError("thumbnail dimensions must be positive")
        normalized = image_format.casefold()
        if normalized not in {"jpeg", "png"}:
            raise ValueError("thumbnail format must be jpeg or png")
        if not 1 <= jpeg_quality <= 100:
            raise ValueError("jpeg_quality must be within 1..100")
        if directory.is_absolute():
            raise ValueError("thumbnail directory must be relative")
        root = project_root.resolve()
        resolved = (root / directory).resolve()
        if resolved != root and root not in resolved.parents:
            raise ValueError("thumbnail directory escapes project root")
        self.enabled = enabled
        self._directory = resolved
        self.width = width
        self.height = height
        self.format = normalized
        self.jpeg_quality = jpeg_quality
        self.replace_existing = replace_existing

    def load(self, person_id: str) -> ThumbnailDTO:
        path = self._path(person_id)
        if not self.enabled or not path.is_file():
            return ThumbnailDTO(person_id, False, 0, 0, self.format)
        try:
            payload = path.read_bytes()
            image = cv2.imdecode(np.frombuffer(payload, np.uint8), cv2.IMREAD_COLOR)
        except OSError as exc:
            raise ThumbnailError("thumbnail could not be loaded") from exc
        if image is None:
            raise ThumbnailError("thumbnail is not a valid image")
        height, width = image.shape[:2]
        return ThumbnailDTO(person_id, True, width, height, self.format, payload)

    def save(
        self, person_id: str, image_bytes: bytes, *, replace: bool | None = None,
    ) -> ThumbnailDTO:
        if not self.enabled:
            return ThumbnailDTO(person_id, False, 0, 0, self.format)
        path = self._path(person_id)
        replacement_allowed = self.replace_existing if replace is None else replace
        if path.exists() and not replacement_allowed:
            raise ThumbnailExistsError("thumbnail already exists; explicit replacement required")
        image = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
        if image is None or image.size == 0:
            raise ThumbnailError("selected thumbnail is not a decodable image")
        resized = cv2.resize(image, (self.width, self.height), interpolation=cv2.INTER_AREA)
        extension = ".jpg" if self.format == "jpeg" else ".png"
        options = ([cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality]
                   if self.format == "jpeg" else [])
        encoded, payload = cv2.imencode(extension, resized, options)
        if not encoded:
            raise ThumbnailError("thumbnail encoding failed")
        self._directory.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{person_id}.", suffix=extension, dir=self._directory
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload.tobytes())
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            raise ThumbnailError("thumbnail could not be written") from exc
        result = self.load(person_id)
        if result.width != self.width or result.height != self.height:
            path.unlink(missing_ok=True)
            raise ThumbnailError("thumbnail dimensions could not be verified")
        return result

    def delete(self, person_id: str) -> bool:
        path = self._path(person_id)
        try:
            if not path.exists():
                return False
            path.unlink()
            return True
        except OSError as exc:
            raise ThumbnailError("thumbnail could not be deleted") from exc

    def exists(self, person_id: str) -> bool:
        return self.enabled and self._path(person_id).is_file()

    def _path(self, person_id: str) -> Path:
        if not SAFE_ID.fullmatch(person_id) or "/" in person_id or ".." in person_id:
            raise ValueError("unsafe person_id for thumbnail")
        suffix = ".jpg" if self.format == "jpeg" else ".png"
        return self._directory / f"{person_id}{suffix}"


def select_thumbnail(samples: Sequence[ThumbnailSample]) -> ThumbnailSample | None:
    accepted = tuple(samples)
    if not accepted:
        return None
    frontal = tuple(item for item in accepted if item.requested_pose == CapturePose.FRONTAL.value)
    pool = frontal or accepted
    return min(pool, key=lambda item: (-item.quality_score, item.sample_index))
