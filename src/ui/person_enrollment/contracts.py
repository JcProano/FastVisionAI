from __future__ import annotations

from enum import Enum


class PersonEnrollmentState(str, Enum):
    IDLE = "IDLE"
    RESERVING_PERSON = "RESERVING_PERSON"
    ENROLLING = "ENROLLING"
    ACTIVATING_PERSON = "ACTIVATING_PERSON"
    ACTIVE = "ACTIVE"
    ROLLING_BACK = "ROLLING_BACK"
    INCONSISTENT = "INCONSISTENT"


class PersonEnrollmentCoordinationError(RuntimeError):
    pass
