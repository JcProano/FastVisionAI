"""Small synchronized holder shared only by web-enrollment use cases."""

from __future__ import annotations

import threading

from ..domain import WebEnrollmentState


class WebEnrollmentSession:
    def __init__(self) -> None:
        self._state = WebEnrollmentState()
        self._lock = threading.RLock()

    def current(self) -> WebEnrollmentState:
        with self._lock:
            return self._state

    def replace(self, state: WebEnrollmentState) -> WebEnrollmentState:
        with self._lock:
            self._state = state
            return state
