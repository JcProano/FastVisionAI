"""UI compatibility facade for the People enrollment use cases."""

from __future__ import annotations

from dataclasses import replace

from src.core.people.application import (
    BeginPersonEnrollmentUseCase,
    CancelPersonEnrollmentUseCase,
    CommitPersonEnrollmentUseCase,
    PersonEnrollmentSession,
)
from src.core.people.domain import PersonEnrollmentState
from src.core.person_database import PersonRepository
from src.engine.gallery import FaceGallery
from src.ui.contracts import (
    EnrollmentProgressDTO,
    EnrollmentResultDTO,
    RegistrationFormData,
    UIState,
)
from src.ui.enrollment_workflow import LocalEnrollmentWorkflow


class _UIEnrollmentResultEditor:
    def coordinated(
        self,
        result: EnrollmentResultDTO,
        *,
        coordination_state: str,
        message: str | None = None,
    ) -> EnrollmentResultDTO:
        changes = {"coordination_state": coordination_state}
        if message is not None:
            changes["message"] = message
        return replace(result, **changes)

    def inconsistent(
        self, person_id: str, reason: str, coordination_state: str
    ) -> EnrollmentResultDTO:
        return EnrollmentResultDTO(
            state=UIState.ERROR,
            person_id=person_id,
            first_name="",
            last_name="",
            display_name="",
            templates_registered=0,
            templates_rejected=0,
            average_quality=0,
            minimum_quality=0,
            maximum_quality=0,
            enrollment_status="inconsistent",
            persistence_requested=False,
            persistence_succeeded=None,
            message=f"{reason}; reconciliación administrativa requerida",
            coordination_state=coordination_state,
        )


class PersonEnrollmentCoordinator:
    """Preserves the UI API while delegating all saga rules to application."""

    def __init__(
        self,
        repository: PersonRepository,
        gallery: FaceGallery,
        workflow: LocalEnrollmentWorkflow,
        audit_callback=None,
    ) -> None:
        self.repository = repository
        self.gallery = gallery
        self.workflow = workflow
        self.audit_callback = audit_callback
        self._session = PersonEnrollmentSession()
        self._begin = BeginPersonEnrollmentUseCase(
            repository, gallery, workflow, self._session
        )
        self._cancel = CancelPersonEnrollmentUseCase(
            repository, workflow, self._session
        )
        self._commit = CommitPersonEnrollmentUseCase(
            repository,
            gallery,
            workflow,
            _UIEnrollmentResultEditor(),
            self._session,
            audit_callback,
        )

    @property
    def state(self) -> PersonEnrollmentState:
        return self._session.state

    @property
    def active(self) -> bool:
        return self.workflow.active

    def begin(self, form: RegistrationFormData) -> EnrollmentProgressDTO:
        return self._begin.execute(form)

    def cancel(self) -> None:
        self._cancel.execute()

    def commit(self) -> EnrollmentResultDTO:
        return self._commit.execute()
