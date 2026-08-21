"""Project engine enrollment progress without biometric payloads."""

from collections.abc import Callable

from ..domain import WebEnrollmentStage, WebEnrollmentState


class GetWebEnrollmentStatusUseCase:
    def __init__(self, session, status: Callable[[], object | None]) -> None:
        self._session = session
        self._status = status

    def execute(self) -> dict[str, object]:
        state = self._session.current()
        raw = self._status()
        progress = getattr(raw, "progress", raw)
        result = getattr(raw, "result", None)
        if result is None and raw is not None and hasattr(
            raw, "templates_registered"
        ):
            result = raw
        if result is None:
            result = state.result
        elif result is not state.result:
            state = self._session.replace(
                WebEnrollmentState(state.stage, state.summary, result)
            )
        if progress is not None and hasattr(progress, "accepted_samples"):
            accepted = int(progress.accepted_samples)
            target = int(progress.target_samples)
            if accepted >= target and state.stage is WebEnrollmentStage.CAPTURE:
                state = self._session.replace(
                    WebEnrollmentState(
                        WebEnrollmentStage.VALIDATION,
                        state.summary,
                        state.result,
                    )
                )
            return self._payload(
                state,
                accepted=accepted,
                target=target,
                instruction=str(progress.instruction),
                quality_score=progress.quality_score,
                quality_band=progress.quality_band,
                can_continue=accepted >= target,
            )
        if result is not None:
            enrolled = str(
                getattr(getattr(result, "enrollment_status", ""), "value", None)
                or getattr(result, "enrollment_status", "")
            ).casefold() == "enrolled"
            if enrolled and state.stage not in {
                WebEnrollmentStage.PHOTO,
                WebEnrollmentStage.PHOTO_CAPTURE,
                WebEnrollmentStage.PHOTO_CONFIRMATION,
                WebEnrollmentStage.CONFIRMATION,
                WebEnrollmentStage.COMPLETE,
            }:
                state = self._session.replace(
                    WebEnrollmentState(
                        WebEnrollmentStage.PHOTO, state.summary, result
                    )
                )
            return self._payload(
                state,
                accepted=int(result.templates_registered),
                target=5,
                instruction="CAPTURA FACIAL COMPLETADA",
                quality_score=result.average_quality,
                quality_band=None,
                can_continue=True,
                success=state.stage is WebEnrollmentStage.COMPLETE,
            )
        return self._payload(
            state,
            accepted=0,
            target=5,
            instruction=None,
            quality_score=None,
            quality_band=None,
            can_continue=state.stage
            in {WebEnrollmentStage.PREPARATION, WebEnrollmentStage.CONFIRMATION},
        )

    @staticmethod
    def _payload(
        state,
        *,
        accepted,
        target,
        instruction,
        quality_score,
        quality_band,
        can_continue,
        success=False,
    ) -> dict[str, object]:
        return {
            "active": state.active,
            "stage": state.stage.value,
            "accepted_samples": accepted,
            "target_samples": target,
            "instruction": instruction,
            "quality_score": quality_score,
            "quality_band": quality_band,
            "can_continue": can_continue,
            "summary": dict(state.summary),
            "success": success,
        }
