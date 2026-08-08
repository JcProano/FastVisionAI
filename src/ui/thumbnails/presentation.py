"""Tk-compatible conversion kept inside the presentation layer."""

from __future__ import annotations

import cv2
import numpy as np

from .contracts import ThumbnailDTO


def thumbnail_to_ppm(thumbnail: ThumbnailDTO) -> bytes | None:
    if not thumbnail.available or thumbnail.image_bytes is None:
        return None
    image = cv2.imdecode(np.frombuffer(thumbnail.image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        return None
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    height, width = rgb.shape[:2]
    return f"P6 {width} {height} 255\n".encode("ascii") + rgb.tobytes(order="C")

