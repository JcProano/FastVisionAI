"""Presentation-only transforms for live video; biometric frames never enter here."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


@dataclass(frozen=True, slots=True)
class VideoPresentation:
    rotation: int = 0
    mirror_horizontal: bool = False
    crop_enabled: bool = False
    crop_top_percent: float = 0.0
    crop_bottom_percent: float = 0.0
    crop_left_percent: float = 0.0
    crop_right_percent: float = 0.0

    def __post_init__(self) -> None:
        if self.rotation not in (0, 90, 180, 270):
            raise ValueError("camera.presentation.rotation must be 0, 90, 180 or 270")
        crops = (self.crop_top_percent, self.crop_bottom_percent,
                 self.crop_left_percent, self.crop_right_percent)
        if any(value < 0 or value >= 100 for value in crops):
            raise ValueError("presentation crop percentages must be within [0, 100)")
        if self.crop_top_percent + self.crop_bottom_percent >= 100:
            raise ValueError("vertical presentation crop must leave visible pixels")
        if self.crop_left_percent + self.crop_right_percent >= 100:
            raise ValueError("horizontal presentation crop must leave visible pixels")


def contain_size(frame_width: int, frame_height: int,
                 available_width: int, available_height: int) -> tuple[int, int]:
    """Largest undistorted size contained by the available presentation area."""
    if min(frame_width, frame_height, available_width, available_height) <= 0:
        return (0, 0)
    scale = min(available_width / frame_width, available_height / frame_height)
    return (max(1, round(frame_width * scale)), max(1, round(frame_height * scale)))


def render_rgb(rgb_bytes: bytes, width: int, height: int,
               available_width: int, available_height: int,
               settings: VideoPresentation) -> tuple[int, int, bytes]:
    """Crop/orient/resize one owned RGB presentation buffer with preserved ratio."""
    image = np.frombuffer(rgb_bytes, np.uint8).reshape((height, width, 3))
    if settings.crop_enabled:
        y1 = round(height * settings.crop_top_percent / 100)
        y2 = height - round(height * settings.crop_bottom_percent / 100)
        x1 = round(width * settings.crop_left_percent / 100)
        x2 = width - round(width * settings.crop_right_percent / 100)
        image = image[y1:y2, x1:x2]
    if settings.rotation:
        image = np.rot90(image, k={90: 3, 180: 2, 270: 1}[settings.rotation])
    if settings.mirror_horizontal:
        image = np.ascontiguousarray(image[:, ::-1])
    display_width, display_height = contain_size(
        image.shape[1], image.shape[0], available_width, available_height,
    )
    if not display_width or not display_height:
        return image.shape[1], image.shape[0], image.tobytes(order="C")
    if (display_width, display_height) != (image.shape[1], image.shape[0]):
        interpolation = cv2.INTER_AREA if display_width < image.shape[1] else cv2.INTER_LINEAR
        image = cv2.resize(image, (display_width, display_height), interpolation=interpolation)
    return display_width, display_height, image.tobytes(order="C")
