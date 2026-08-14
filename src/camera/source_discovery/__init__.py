"""Safe camera-source discovery and selection boundary."""

from .contracts import CameraDiscoveryConfig, CameraSourceDTO, CameraSourceType, NetworkSourceConfig
from .discovery import CameraSourceDiscovery
from .selection import (
    CameraSelectionController, CameraSelectionResult, camera_config_for_source,
    classify_camera_source, parse_discovery_config,
)
from .redaction import redact_url
from .configuration import CameraConfigurationPersistence

__all__ = [
    "CameraConfigurationPersistence", "CameraDiscoveryConfig", "CameraSelectionController", "CameraSelectionResult",
    "CameraSourceDTO", "CameraSourceDiscovery", "CameraSourceType", "NetworkSourceConfig",
    "camera_config_for_source", "classify_camera_source", "parse_discovery_config", "redact_url",
]
