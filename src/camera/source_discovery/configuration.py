from __future__ import annotations

from typing import Protocol

from .contracts import CameraDiscoveryConfig


class ConfigurationServiceLike(Protocol):
    def current(self): ...
    def save(self, candidate): ...


class CameraConfigurationPersistence:
    """Persist camera discovery settings through Configuration Manager atomically."""

    def __init__(self, service: ConfigurationServiceLike) -> None:
        self.service = service

    def save(self, config: CameraDiscoveryConfig) -> bool:
        candidate = self.service.current().as_mapping()
        candidate["camera"] = {
            "source": config.source,
            "auto_discovery": config.auto_discovery,
            "scan_indices": config.scan_indices,
            "preferred_source": config.preferred_source,
            "network_sources": [
                {"id": item.source_id, "type": item.source_type.value,
                 "name": item.name, "url": item.url}
                for item in config.network_sources
            ],
        }
        return bool(self.service.save(candidate).success)
