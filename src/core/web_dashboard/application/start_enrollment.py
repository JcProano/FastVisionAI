"""Start the web enrollment only from an explicit unregistered presentation."""

from ..domain import WebEnrollmentError, WebEnrollmentStage, WebEnrollmentState


class StartWebEnrollmentUseCase:
    def __init__(self, session) -> None:
        self._session = session

    def execute(self, presentation_kind: str) -> WebEnrollmentState:
        if presentation_kind not in {"UNKNOWN", "GALLERY_UNREGISTERED"}:
            raise WebEnrollmentError(
                "El registro requiere una persona no registrada."
            )
        return self._session.replace(
            WebEnrollmentState(WebEnrollmentStage.PERSON)
        )
