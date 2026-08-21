"""People domain and application errors."""


class PersonDataValidationError(ValueError):
    """Safe validation failure that never asserts real-world identity."""


class PersonRepositoryError(RuntimeError):
    pass


class DuplicatePersonIdError(PersonRepositoryError):
    pass


class DuplicateCedulaError(PersonRepositoryError):
    pass


class PersonNotFoundError(PersonRepositoryError):
    pass


class PersonStatusTransitionError(ValueError):
    pass


class PersonEnrollmentCoordinationError(RuntimeError):
    pass


class ExistingActivePersonError(PersonEnrollmentCoordinationError):
    def __init__(self, person_id: str) -> None:
        super().__init__("Esta persona ya está registrada.")
        self.person_id = person_id


class ExistingPendingPersonError(PersonEnrollmentCoordinationError):
    def __init__(self, person_id: str) -> None:
        super().__init__(
            "Existe un registro biométrico pendiente; requiere resolución "
            "administrativa."
        )
        self.person_id = person_id


class ExistingDisabledPersonError(PersonEnrollmentCoordinationError):
    def __init__(self, person_id: str) -> None:
        super().__init__(
            "La persona existe pero está deshabilitada. Reactívela explícitamente."
        )
        self.person_id = person_id
