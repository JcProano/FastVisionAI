"""Composition root for framework-independent web dashboard use cases."""

from __future__ import annotations

from dataclasses import dataclass

from .application import (
    BeginWebEnrollmentCaptureUseCase,
    CancelWebEnrollmentUseCase,
    ConfirmWebEnrollmentUseCase,
    GetWebEnrollmentStatusUseCase,
    SelectWebEnrollmentPhotoUseCase,
    StartWebEnrollmentUseCase,
    SubmitWebEnrollmentPersonUseCase,
    WebEnrollmentSession,
)


@dataclass(frozen=True, slots=True)
class WebEnrollmentUseCases:
    start: StartWebEnrollmentUseCase
    submit_person: SubmitWebEnrollmentPersonUseCase
    begin_capture: BeginWebEnrollmentCaptureUseCase
    select_photo: SelectWebEnrollmentPhotoUseCase
    confirm: ConfirmWebEnrollmentUseCase
    cancel: CancelWebEnrollmentUseCase
    get_status: GetWebEnrollmentStatusUseCase


class WebEnrollmentContainer:
    @staticmethod
    def build(
        *,
        submit_person,
        begin_capture,
        start_photo,
        capture_photo,
        confirm_photo,
        cancel,
        get_status,
        session_type=WebEnrollmentSession,
    ) -> WebEnrollmentUseCases:
        session = session_type()
        return WebEnrollmentUseCases(
            start=StartWebEnrollmentUseCase(session),
            submit_person=SubmitWebEnrollmentPersonUseCase(
                session, submit_person
            ),
            begin_capture=BeginWebEnrollmentCaptureUseCase(
                session, begin_capture
            ),
            select_photo=SelectWebEnrollmentPhotoUseCase(
                session,
                start=start_photo,
                capture=capture_photo,
                confirm=confirm_photo,
            ),
            confirm=ConfirmWebEnrollmentUseCase(session),
            cancel=CancelWebEnrollmentUseCase(session, cancel),
            get_status=GetWebEnrollmentStatusUseCase(session, get_status),
        )
