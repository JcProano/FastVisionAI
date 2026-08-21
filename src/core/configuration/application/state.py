"""Shared thread-safe state for independent configuration operations."""

import threading

from ..domain.models import ConfigurationSnapshot


class ConfigurationSession:
    def __init__(self, current: ConfigurationSnapshot) -> None:
        self._current = current
        self.restart_required_pending = False
        self._lock = threading.RLock()

    def current(self) -> ConfigurationSnapshot:
        with self._lock:
            return self._current

    def replace(
        self, snapshot: ConfigurationSnapshot, *, restart_required: bool
    ) -> None:
        with self._lock:
            self._current = snapshot
            self.restart_required_pending = restart_required
