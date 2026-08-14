from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Mapping


class CameraSourceType(str, Enum):
    LOCAL_V4L2 = "LOCAL_V4L2"
    NETWORK_RTSP = "NETWORK_RTSP"
    NETWORK_HTTP = "NETWORK_HTTP"
    CUSTOM = "CUSTOM"


@dataclass(frozen=True, slots=True)
class CameraSourceDTO:
    """Presentation-safe source descriptor; it never contains a device path or URL."""

    source_id: str
    source_type: CameraSourceType
    display_name: str
    available: bool
    preferred: bool = False
    details: Mapping[str, str | int | bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "details", MappingProxyType(dict(self.details)))


@dataclass(frozen=True, slots=True)
class NetworkSourceConfig:
    source_id: str
    source_type: CameraSourceType
    name: str
    url: str


@dataclass(frozen=True, slots=True)
class CameraDiscoveryConfig:
    source: int | str = 0
    auto_discovery: bool = False
    scan_indices: int = 10
    preferred_source: str | None = None
    network_sources: tuple[NetworkSourceConfig, ...] = ()
