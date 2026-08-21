"""Explicit state shared only by the three enrollment use cases."""

from __future__ import annotations

import threading

from ..domain.errors import PersonEnrollmentCoordinationError
from ..domain.models import PersonEnrollmentState


class PersonEnrollmentSession:
    def __init__(self) -> None:
        self.state = PersonEnrollmentState.IDLE
        self.reserved_person_id: str | None = None
        self.lock = threading.RLock()

    def require(self, expected: PersonEnrollmentState) -> None:
        if self.state is not expected:
            raise PersonEnrollmentCoordinationError(
                f"invalid coordinator transition from {self.state.value}"
            )
