"""Tk-compatible conversion kept inside the presentation layer."""

from __future__ import annotations

import cv2
import numpy as np

from .contracts import ThumbnailDTO


def thumbnail_to_ppm(
    thumbnail: ThumbnailDTO, *, max_width: int | None = None,
    max_height: int | None = None, allow_upscale: bool = False,
) -> bytes | None:
    if not thumbnail.available or thumbnail.image_bytes is None:
        return None
    image = cv2.imdecode(np.frombuffer(thumbnail.image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        return None
    if max_width is not None or max_height is not None:
        if max_width is not None and max_width <= 0:
            raise ValueError("max_width must be positive")
        if max_height is not None and max_height <= 0:
            raise ValueError("max_height must be positive")
        height, width = image.shape[:2]
        width_limit = width if max_width is None else max_width
        height_limit = height if max_height is None else max_height
        scale = min(width_limit / width, height_limit / height)
        if not allow_upscale:
            scale = min(scale, 1.0)
        target = (max(1, round(width * scale)), max(1, round(height * scale)))
        if target != (width, height):
            interpolation = cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA
            image = cv2.resize(image, target, interpolation=interpolation)
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    height, width = rgb.shape[:2]
    return f"P6 {width} {height} 255\n".encode("ascii") + rgb.tobytes(order="C")
