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


class ExistingActivePersonError(PersonEnrollmentCoordinationError):
    def __init__(self, person_id: str) -> None:
        super().__init__("Esta persona ya está registrada.")
        self.person_id = person_id


class ExistingPendingPersonError(PersonEnrollmentCoordinationError):
    def __init__(self, person_id: str) -> None:
        super().__init__(
            "Existe un registro biométrico pendiente; requiere resolución administrativa."
        )
        self.person_id = person_id


class ExistingDisabledPersonError(PersonEnrollmentCoordinationError):
    def __init__(self, person_id: str) -> None:
        super().__init__(
            "La persona existe pero está deshabilitada. Reactívela explícitamente."
        )
        self.person_id = person_id
