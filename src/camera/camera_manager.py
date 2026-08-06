"""OpenCV based capture manager for phase 1."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any, Protocol

import cv2

from src.camera.camera_types import CameraConfig, CameraReadResult, ReadStatus
from src.camera.frame import Frame

LOGGER = logging.getLogger(__name__)


class VideoCaptureLike(Protocol):
    def set(self, property_id: int, value: float) -> bool: ...
    def open(self, source: int | str) -> bool: ...
    def isOpened(self) -> bool: ...
    def read(self) -> tuple[bool, Any]: ...
    def release(self) -> None: ...


CaptureFactory = Callable[[], VideoCaptureLike]


class CameraManager:
    """Own one capture and reconnect live sources within configured bounds."""

    def __init__(
        self,
        config: CameraConfig,
        cancel_event: threading.Event | None = None,
        capture_factory: CaptureFactory | None = None,
    ) -> None:
        self.config = config
        self.cancel_event = cancel_event or threading.Event()
        self._capture_factory = capture_factory or cv2.VideoCapture
        self._capture: VideoCaptureLike | None = None
        self.connected = False
        self._sequence_id = 0
        self.connection_id = 0
        self.reconnection_count = 0
        self.last_recovery_seconds: float | None = None

    def __enter__(self) -> CameraManager:
        self.open()
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.release()

    def cancel(self) -> None:
        """Request cancellation; waits between reconnects stop immediately."""

        self.cancel_event.set()

    def open(self) -> bool:
        """Open the configured source once."""

        if self.cancel_event.is_set():
            return False
        self.release()
        capture = self._capture_factory()
        self._set_timeout(capture, "CAP_PROP_OPEN_TIMEOUT_MSEC", self.config.open_timeout_ms)
        self._set_timeout(capture, "CAP_PROP_READ_TIMEOUT_MSEC", self.config.read_timeout_ms)

        try:
            opened = bool(capture.open(self.config.source))
            self.connected = opened and bool(capture.isOpened())
        except (cv2.error, OSError, RuntimeError) as exc:
            LOGGER.error("Error abriendo cámara '%s': %s", self.config.name, exc)
            self.connected = False

        if self.connected:
            self._capture = capture
            self.connection_id += 1
            LOGGER.info("Fuente '%s' conectada (%s)", self.config.name, self.config.camera_type.value)
            return True

        capture.release()
        LOGGER.warning("No se pudo abrir la fuente '%s'", self.config.name)
        return False

    def read(self) -> CameraReadResult:
        """Read one frame and automatically recover bounded live-source failures."""

        if self.cancel_event.is_set():
            return CameraReadResult(ReadStatus.CANCELLED)
        if not self.connected and not self.open():
            if not self.config.is_live or not self._reconnect():
                return CameraReadResult(
                    ReadStatus.CANCELLED if self.cancel_event.is_set() else ReadStatus.DISCONNECTED
                )

        ok, frame = self._read_capture()
        if ok:
            return CameraReadResult(ReadStatus.FRAME, self._make_frame(frame))

        self.connected = False
        if not self.config.is_live:
            LOGGER.info("Fin normal del archivo de video '%s'", self.config.name)
            self.release()
            return CameraReadResult(ReadStatus.EOF)

        LOGGER.warning("Se perdió la fuente en vivo '%s'", self.config.name)
        outage_started = time.monotonic()
        if not self._reconnect():
            return CameraReadResult(
                ReadStatus.CANCELLED if self.cancel_event.is_set() else ReadStatus.DISCONNECTED
            )
        ok, frame = self._read_capture()
        if ok:
            self.reconnection_count += 1
            self.last_recovery_seconds = time.monotonic() - outage_started
            LOGGER.info(
                "Stream '%s' recuperado en %.3f s sin reiniciar el servicio",
                self.config.name,
                self.last_recovery_seconds,
            )
            return CameraReadResult(ReadStatus.FRAME, self._make_frame(frame))
        return CameraReadResult(ReadStatus.DISCONNECTED)

    def release(self) -> None:
        capture, self._capture = self._capture, None
        self.connected = False
        if capture is not None:
            try:
                capture.release()
            except (cv2.error, OSError, RuntimeError) as exc:
                LOGGER.warning("Error liberando cámara '%s': %s", self.config.name, exc)

    def _read_capture(self) -> tuple[bool, Any]:
        if self._capture is None:
            return False, None
        try:
            return self._capture.read()
        except (cv2.error, OSError, RuntimeError) as exc:
            LOGGER.warning("Error leyendo cámara '%s': %s", self.config.name, exc)
            return False, None

    def _make_frame(self, image: Any) -> Frame:
        self._sequence_id += 1
        return Frame.create(
            image,
            sequence_id=self._sequence_id,
            source_name=self.config.name,
            monotonic_timestamp=time.monotonic(),
            connection_id=self.connection_id,
        )

    def _reconnect(self) -> bool:
        reconnect = self.config.reconnect
        if not self.config.is_live or not reconnect.enabled:
            self.release()
            return False

        for attempt in range(1, reconnect.max_attempts + 1):
            self.release()
            if self.cancel_event.wait(reconnect.interval_seconds):
                return False
            LOGGER.info("Reconexión de '%s': intento %d/%d", self.config.name, attempt, reconnect.max_attempts)
            if self.open():
                return True
        LOGGER.error("Se agotaron los intentos de reconexión de '%s'", self.config.name)
        return False

    @staticmethod
    def _set_timeout(capture: VideoCaptureLike, property_name: str, value: int) -> None:
        property_id = getattr(cv2, property_name, None)
        if property_id is not None and value > 0:
            try:
                capture.set(property_id, float(value))
            except (cv2.error, OSError, RuntimeError):
                LOGGER.debug("El backend de OpenCV no admite %s", property_name)
