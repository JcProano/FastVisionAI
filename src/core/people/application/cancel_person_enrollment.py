"""Use case for cancelling enrollment and removing its civil reservation."""

from ..domain.models import PersonEnrollmentState
from ..domain.ports import BiometricEnrollmentWorkflowPort, PeopleRepositoryPort
from ._enrollment_support import delete_pending_verified
from .enrollment_session import PersonEnrollmentSession


class CancelPersonEnrollmentUseCase:
    def __init__(
        self,
        repository: PeopleRepositoryPort,
        workflow: BiometricEnrollmentWorkflowPort,
        session: PersonEnrollmentSession,
    ) -> None:
        self._repository = repository
        self._workflow = workflow
        self._session = session

    def execute(self) -> None:
        with self._session.lock:
            if self._workflow.active:
                self._workflow.cancel()
            delete_pending_verified(
                self._repository, self._session.reserved_person_id
            )
            self._session.reserved_person_id = None
            self._session.state = PersonEnrollmentState.IDLE
