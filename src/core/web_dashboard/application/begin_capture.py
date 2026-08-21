"""Begin or continue manual biometric sample capture."""

from collections.abc import Callable, Mapping

from ..domain import WebEnrollmentError, WebEnrollmentStage, WebEnrollmentState


class BeginWebEnrollmentCaptureUseCase:
    def __init__(self, session, capture: Callable[[Mapping[str, object]], object]) -> None:
        self._session = session
        self._capture = capture

    def execute(self, payload: Mapping[str, object]) -> object:
        state = self._session.current()
        if state.stage not in {
            WebEnrollmentStage.PREPARATION,
            WebEnrollmentStage.CAPTURE,
        }:
            raise WebEnrollmentError("Captura no disponible.")
        result = self._capture(payload)
        self._session.replace(
            WebEnrollmentState(
                WebEnrollmentStage.CAPTURE, state.summary, state.result
            )
        )
        return result
