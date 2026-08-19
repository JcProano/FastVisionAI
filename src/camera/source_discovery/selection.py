from __future__ import annotations

from dataclasses import dataclass, replace
from collections.abc import Callable
import uuid

from src.camera.camera_types import CameraConfig, CameraType, ReconnectConfig

from .contracts import CameraDiscoveryConfig, CameraSourceDTO, CameraSourceType, NetworkSourceConfig
from .discovery import CameraSourceDiscovery


@dataclass(frozen=True, slots=True)
class CameraSelectionResult:
    sources: tuple[CameraSourceDTO, ...]
    selected: CameraSourceDTO | None
    requires_selection: bool
    preferred_unavailable: bool = False


class CameraSelectionController:
    """Selection policy and defense-in-depth guard independent from Tk."""

    def __init__(self, discovery: CameraSourceDiscovery, *, switch_allowed=lambda: True,
                 persist_config: Callable[[CameraDiscoveryConfig], bool] | None = None) -> None:
        self.discovery = discovery
        self._switch_allowed = switch_allowed
        self._persist_config = persist_config
        self.sources: tuple[CameraSourceDTO, ...] = ()

    def refresh(self) -> CameraSelectionResult:
        self.sources = self.discovery.refresh()
        configured_preference = self.discovery.config.preferred_source
        preferred = next((item for item in self.sources if item.preferred and item.available), None)
        valid = tuple(item for item in self.sources if item.available)
        # A saved primary camera is an explicit user decision.  Never replace it
        # with another discovered source merely because it happens to be usable.
        if configured_preference is not None:
            return CameraSelectionResult(
                self.sources, preferred, preferred is None, preferred is None,
            )
        selected = valid[0] if len(valid) == 1 else None
        return CameraSelectionResult(self.sources, selected, selected is None and len(valid) > 1)

    def use(self, source_id: str) -> CameraSourceDTO:
        if not self._switch_allowed():
            raise PermissionError("No se puede cambiar de cámara durante un registro.")
        source = next((item for item in self.sources if item.source_id == source_id and item.available), None)
        if source is None:
            raise ValueError("La fuente seleccionada ya no está disponible.")
        return source

    def probe(self, source_id: str) -> bool:
        return self.discovery.probe(source_id)

    def add_network_source(self, name: str, source_type: CameraSourceType, url: str) -> CameraSourceDTO:
        raw = {"source": self.discovery.config.source,
               "auto_discovery": self.discovery.config.auto_discovery,
               "scan_indices": self.discovery.config.scan_indices,
               "preferred_source": self.discovery.config.preferred_source,
               "network_sources": [
                   {"id": item.source_id, "type": item.source_type.value,
                    "name": item.name, "url": item.url}
                   for item in self.discovery.config.network_sources
               ] + [{"id": f"network-{uuid.uuid4()}", "type": source_type.value,
                     "name": name.strip(), "url": url.strip()}]}
        updated = parse_discovery_config(raw)
        self._persist(updated)
        self.discovery.config = updated
        result = self.refresh()
        return result.sources[-1]

    def probe_network_source(self, name: str, source_type: CameraSourceType, url: str) -> bool:
        candidate = parse_discovery_config({
            "source": self.discovery.config.source, "auto_discovery": False,
            "scan_indices": self.discovery.config.scan_indices,
            "network_sources": [{"id": "probe", "type": source_type.value,
                                 "name": name.strip(), "url": url.strip()}],
        }).network_sources[0]
        return self.discovery.probe_network_url(candidate.url)

    def set_preferred(self, source_id: str | None) -> None:
        if source_id is not None and not any(item.source_id == source_id for item in self.sources):
            raise ValueError("La cámara preferida no existe.")
        updated = replace(
            self.discovery.config, source="auto", auto_discovery=True,
            preferred_source=source_id,
        )
        self._persist(updated)
        self.discovery.config = updated

    def _persist(self, config: CameraDiscoveryConfig) -> None:
        if self._persist_config is None or not self._persist_config(config):
            raise RuntimeError("No se pudo guardar la configuración de cámara.")


def camera_config_for_source(
    source: CameraSourceDTO, discovery_config: CameraDiscoveryConfig,
    *, reconnect: ReconnectConfig | None = None,
) -> CameraConfig:
    if source.source_type is CameraSourceType.LOCAL_V4L2:
        concrete: int | str = int(source.details["index"])
        camera_type = CameraType.USB
    else:
        configured = next(
            (item for item in discovery_config.network_sources if item.source_id == source.source_id), None
        )
        if configured is None:
            raise ValueError("La fuente de red no existe en la configuración.")
        concrete = configured.url
        camera_type = CameraType.RTSP
    return CameraConfig(source.display_name, camera_type, concrete, reconnect=reconnect or ReconnectConfig())


def classify_camera_source(source: int | str) -> CameraType:
    if isinstance(source, int):
        return CameraType.USB
    lowered = source.lower()
    if lowered.startswith(("rtsp://", "http://", "https://")):
        return CameraType.RTSP
    return CameraType.USB


def parse_discovery_config(value: object) -> CameraDiscoveryConfig:
    if not isinstance(value, dict):
        raise ValueError("camera configuration must be an object")
    source = value.get("source", 0)
    if not ((isinstance(source, int) and not isinstance(source, bool) and source >= 0)
            or source == "auto" or (
                isinstance(source, str)
                and source.lower().startswith(("rtsp://", "http://", "https://"))
            )):
        raise ValueError("camera.source must be a non-negative index, auto, RTSP or HTTP URL")
    scan_indices = value.get("scan_indices", 10)
    if isinstance(scan_indices, bool) or not isinstance(scan_indices, int) or scan_indices <= 0:
        raise ValueError("camera.scan_indices must be a positive integer")
    preferred = value.get("preferred_source")
    if preferred is not None and (not isinstance(preferred, str) or not preferred):
        raise ValueError("camera.preferred_source must be null or a source id")
    raw_network = value.get("network_sources", [])
    if not isinstance(raw_network, list):
        raise ValueError("camera.network_sources must be a list")
    network = []
    for index, item in enumerate(raw_network):
        if not isinstance(item, dict):
            raise ValueError(f"camera.network_sources[{index}] must be an object")
        source_id, name, url = item.get("id"), item.get("name"), item.get("url")
        try:
            source_type = CameraSourceType(item.get("type"))
        except (TypeError, ValueError) as exc:
            raise ValueError("network source type must be NETWORK_RTSP or NETWORK_HTTP") from exc
        expected = (("rtsp://",) if source_type is CameraSourceType.NETWORK_RTSP else
                    ("http://", "https://") if source_type is CameraSourceType.NETWORK_HTTP else
                    None if source_type is CameraSourceType.CUSTOM else ())
        if expected == ():
            raise ValueError("network source type must be NETWORK_RTSP, NETWORK_HTTP or CUSTOM")
        if not all(isinstance(part, str) and part for part in (source_id, name, url)):
            raise ValueError("network source id, name and url are required")
        if expected is not None and not url.lower().startswith(expected):
            raise ValueError("network source URL does not match its type")
        network.append(NetworkSourceConfig(source_id, source_type, name[:120], url))
    auto = value.get("auto_discovery", False)
    if type(auto) is not bool:
        raise ValueError("camera.auto_discovery must be boolean")
    return CameraDiscoveryConfig(source, auto, scan_indices, preferred, tuple(network))
