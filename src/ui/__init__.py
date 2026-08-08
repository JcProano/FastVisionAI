"""Isolated local UI for experimental candidate display and enrollment."""

from src.ui.contracts import (
    EnrollmentProgressDTO, EnrollmentResultDTO, ErrorDTO, MonitoringDTO,
    RegistrationFormData, UIState,
)
from src.ui.controller import LocalFaceUIController
from src.ui.enrollment_workflow import EnrollmentAlreadyActiveError, LocalEnrollmentWorkflow
from src.ui.form_validation import RegistrationFormError, validate_registration_form
from src.ui.recognition_session import ExperimentalRecognitionSession
from src.ui.live_session import LiveFaceSession
from src.ui.people import PeopleManagerController, PeopleManagerState

__all__ = [
    "EnrollmentAlreadyActiveError", "EnrollmentProgressDTO", "EnrollmentResultDTO",
    "ErrorDTO", "ExperimentalRecognitionSession", "LocalEnrollmentWorkflow",
    "LiveFaceSession", "LocalFaceUIController", "MonitoringDTO", "PeopleManagerController",
    "PeopleManagerState", "RegistrationFormData",
    "RegistrationFormError", "UIState", "validate_registration_form",
]
