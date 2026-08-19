from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

import cv2

from .contracts import CameraDiscoveryConfig, CameraSourceDTO, CameraSourceType
from .redaction import redact_url

LOGGER = logging.getLogger(__name__)


class ProbeCapture(Protocol):
    def set(self, property_id: int, value: float) -> bool: ...
    def open(self, source: int | str) -> bool: ...
    def isOpened(self) -> bool: ...
    def read(self) -> tuple[bool, Any]: ...
    def release(self) -> None: ...


class CameraSourceDiscovery:
    """Probe local V4L2 indices and expose manually configured network sources."""

    def __init__(
        self, config: CameraDiscoveryConfig, *, capture_factory: Callable[[], ProbeCapture] | None = None,
        path_exists: Callable[[Path], bool] | None = None,
        name_reader: Callable[[Path], str] | None = None,
        occupied_source_id: Callable[[], str | None] | None = None,
        probe_network_sources: bool = False,
        network_source_ids_to_probe: frozenset[str] | None = None,
        open_timeout_ms: int = 1_500, read_timeout_ms: int = 1_500,
    ) -> None:
        self.config = config
        self._capture_factory = capture_factory or cv2.VideoCapture
        self._path_exists = path_exists or Path.exists
        self._name_reader = name_reader or (lambda path: path.read_text(encoding="utf-8"))
        self._occupied_source_id = occupied_source_id or (lambda: None)
        self._probe_network_sources = probe_network_sources
        self._network_source_ids_to_probe = network_source_ids_to_probe
        self.open_timeout_ms = open_timeout_ms
        self.read_timeout_ms = read_timeout_ms

    def discover(self) -> tuple[CameraSourceDTO, ...]:
        local = tuple(
            source for index in range(self.config.scan_indices)
            if (source := self.probe_local(index)) is not None
        ) if self.config.auto_discovery or self.config.source == "auto" else ()
        network = tuple(self._network_dto(item) for item in self.config.network_sources)
        return local + network

    def refresh(self) -> tuple[CameraSourceDTO, ...]:
        return self.discover()

    def probe_local(self, index: int) -> CameraSourceDTO | None:
        device = Path(f"/dev/video{index}")
        # Linux offers a cheap existence filter. Tests/backends may explicitly opt out.
        if not self._path_exists(device):
            return None
        if self._occupied_source_id() == f"v4l2:{index}":
            name = self._safe_name(index)
            return CameraSourceDTO(
                f"v4l2:{index}", CameraSourceType.LOCAL_V4L2, name, True,
                f"v4l2:{index}" == self.config.preferred_source,
                {"index": index, "transport": "V4L2", "virtual": self._is_virtual(name),
                 "in_use": True},
            )
        available = self._probe_capture(index, f"V4L2 index {index}")
        if not available:
            return None
        name = self._safe_name(index)
        return CameraSourceDTO(
            f"v4l2:{index}", CameraSourceType.LOCAL_V4L2, name, True,
            f"v4l2:{index}" == self.config.preferred_source,
            {"index": index, "transport": "V4L2", "virtual": self._is_virtual(name)},
        )

    def _safe_name(self, index: int) -> str:
        try:
            value = self._name_reader(Path(f"/sys/class/video4linux/video{index}/name")).strip()
        except (OSError, UnicodeError):
            value = ""
        return value[:120] if value else f"Cámara de video #{index}"

    def _network_dto(self, item) -> CameraSourceDTO:
        should_probe = self._probe_network_sources and (
            self._network_source_ids_to_probe is None
            or item.source_id in self._network_source_ids_to_probe
        )
        available = self._probe_capture(item.url, "network camera") if should_probe else True
        return CameraSourceDTO(
            item.source_id, item.source_type, item.name, available,
            item.source_id == self.config.preferred_source,
            {"transport": ("RTSP" if item.source_type is CameraSourceType.NETWORK_RTSP else
                           "HTTP/MJPEG" if item.source_type is CameraSourceType.NETWORK_HTTP else "Personalizada"),
             "endpoint": redact_url(item.url)},
        )

    def probe(self, source_id: str) -> bool:
        """Actively test one source, except the capture already owned by the session."""
        if source_id == self._occupied_source_id():
            return True
        if source_id.startswith("v4l2:"):
            try: index = int(source_id.partition(":")[2])
            except ValueError: return False
            return self._path_exists(Path(f"/dev/video{index}")) and self._probe_capture(
                index, f"V4L2 index {index}",
            )
        network = next((item for item in self.config.network_sources
                        if item.source_id == source_id), None)
        return False if network is None else self._probe_capture(network.url, "network camera")

    def probe_network_url(self, url: str) -> bool:
        return self._probe_capture(url, "network camera")

    def _probe_capture(self, source: int | str, safe_name: str) -> bool:
        capture = self._capture_factory()
        try:
            self._set_timeout(capture, "CAP_PROP_OPEN_TIMEOUT_MSEC", self.open_timeout_ms)
            self._set_timeout(capture, "CAP_PROP_READ_TIMEOUT_MSEC", self.read_timeout_ms)
            opened = bool(capture.open(source))
            if not (opened and bool(capture.isOpened())):
                return False
            ok, frame = capture.read()
            return bool(ok and frame is not None)
        except (cv2.error, OSError, RuntimeError) as exc:
            LOGGER.debug("Camera probe failed for %s: %s", safe_name, exc)
            return False
        finally:
            try: capture.release()
            except (cv2.error, OSError, RuntimeError):
                LOGGER.debug("Camera probe release failed for %s", safe_name)

    @staticmethod
    def _is_virtual(name: str) -> bool:
        lowered = name.casefold()
        return any(marker in lowered for marker in ("droidcam", "obs", "virtual", "loopback"))

    @staticmethod
    def _set_timeout(capture: ProbeCapture, name: str, value: int) -> None:
        property_id = getattr(cv2, name, None)
        if property_id is not None and value > 0:
            try:
                capture.set(property_id, float(value))
            except (cv2.error, OSError, RuntimeError):
                pass
