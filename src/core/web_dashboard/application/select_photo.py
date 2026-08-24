"""Handle the explicit optional-photo decisions after biometric enrollment."""

from collections.abc import Callable, Mapping

from ..domain import WebEnrollmentError, WebEnrollmentStage, WebEnrollmentState


class SelectWebEnrollmentPhotoUseCase:
    def __init__(
        self,
        session,
        *,
        start: Callable[[Mapping[str, object]], object],
        capture: Callable[[Mapping[str, object]], object],
        confirm: Callable[[Mapping[str, object]], object],
    ) -> None:
        self._session = session
        self._start = start
        self._capture = capture
        self._confirm = confirm

    def execute(self, choice: str, payload: Mapping[str, object]) -> object:
        state = self._session.current()
        normalized = choice.upper()
        if normalized == "TAKE":
            self._require_stage(state, WebEnrollmentStage.PHOTO)
            result = self._start(payload)
            next_stage = WebEnrollmentStage.PHOTO_CAPTURE
        elif normalized == "CAPTURE":
            self._require_stage(
                state,
                WebEnrollmentStage.PHOTO_CAPTURE,
                WebEnrollmentStage.PHOTO_CONFIRMATION,
            )
            result = self._capture(payload)
            next_stage = WebEnrollmentStage.PHOTO_CONFIRMATION
        elif normalized == "CONFIRM":
            self._require_stage(
                state, WebEnrollmentStage.PHOTO_CONFIRMATION
            )
            result = self._confirm(payload)
            next_stage = WebEnrollmentStage.CONFIRMATION
        elif normalized == "SKIP":
            self._require_stage(state, WebEnrollmentStage.PHOTO)
            result = True
            next_stage = WebEnrollmentStage.CONFIRMATION
        else:
            raise WebEnrollmentError("Acción de fotografía inválida.")
        self._session.replace(
            WebEnrollmentState(next_stage, state.summary, state.result)
        )
        return result

    @staticmethod
    def _require_stage(state, *allowed: WebEnrollmentStage) -> None:
        if state.stage not in allowed:
            raise WebEnrollmentError("Fotografía no disponible.")
