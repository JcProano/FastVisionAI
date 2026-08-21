"""Cancel the workflow through the biometric rollback boundary."""

from collections.abc import Callable, Mapping

from ..domain import WebEnrollmentState


class CancelWebEnrollmentUseCase:
    def __init__(self, session, cancel: Callable[[Mapping[str, object]], object]) -> None:
        self._session = session
        self._cancel = cancel

    def execute(self, payload: Mapping[str, object]) -> object:
        result = self._cancel(payload)
        self._session.replace(WebEnrollmentState())
        return result
