"""Confirm the final civil/biometric summary."""

from ..domain import WebEnrollmentError, WebEnrollmentStage, WebEnrollmentState


class ConfirmWebEnrollmentUseCase:
    def __init__(self, session) -> None:
        self._session = session

    def execute(self) -> bool:
        state = self._session.current()
        if state.stage is not WebEnrollmentStage.CONFIRMATION:
            raise WebEnrollmentError("Confirmación no disponible.")
        self._session.replace(
            WebEnrollmentState(
                WebEnrollmentStage.COMPLETE, state.summary, state.result
            )
        )
        return True
