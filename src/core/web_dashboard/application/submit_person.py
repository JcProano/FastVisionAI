"""Validate the active stage and reserve civil data through the people boundary."""

from collections.abc import Callable, Mapping

from ..domain import WebEnrollmentError, WebEnrollmentStage, WebEnrollmentState


class SubmitWebEnrollmentPersonUseCase:
    SUMMARY_FIELDS = (
        "first_name",
        "last_name",
        "cedula",
        "position",
        "department",
        "company",
    )

    def __init__(self, session, submit: Callable[[Mapping[str, object]], object]) -> None:
        self._session = session
        self._submit = submit

    def execute(self, payload: Mapping[str, object]) -> object:
        if self._session.current().stage is not WebEnrollmentStage.PERSON:
            raise WebEnrollmentError("Etapa de datos no activa.")
        result = self._submit(payload)
        if result is False:
            raise RuntimeError("No se pudo iniciar enrollment.")
        summary = {
            key: str(payload.get(key, ""))[:200] for key in self.SUMMARY_FIELDS
        }
        self._session.replace(
            WebEnrollmentState(WebEnrollmentStage.PREPARATION, summary)
        )
        return result
