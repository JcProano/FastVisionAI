"""Typed models shared by the Camera Engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TypeAlias

from src.camera.frame import Frame

CameraSource: TypeAlias = int | str


class CameraType(str, Enum):
    """Capture sources supported during phase 1."""

    USB = "usb"
    NETWORK_HTTP = "network_http"
    RTSP = "rtsp"
    VIDEO_FILE = "video_file"


class ReadStatus(str, Enum):
    """Outcome of a CameraManager read operation."""

    FRAME = "frame"
    EOF = "eof"
    DISCONNECTED = "disconnected"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class ReconnectConfig:
    enabled: bool = True
    max_attempts: int = 3
    interval_seconds: float = 1.0


@dataclass(frozen=True, slots=True)
class CameraConfig:
    name: str
    camera_type: CameraType
    source: CameraSource
    open_timeout_ms: int = 5_000
    read_timeout_ms: int = 5_000
    reconnect: ReconnectConfig = field(default_factory=ReconnectConfig)

    @property
    def is_live(self) -> bool:
        return self.camera_type in {CameraType.USB, CameraType.NETWORK_HTTP, CameraType.RTSP}

    @property
    def video_path(self) -> Path | None:
        if self.camera_type is CameraType.VIDEO_FILE:
            return Path(str(self.source))
        return None


@dataclass(frozen=True, slots=True)
class CameraReadResult:
    status: ReadStatus
    frame: Frame | None = None
