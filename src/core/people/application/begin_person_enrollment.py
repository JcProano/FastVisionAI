"""Use case for reserving civil data and beginning biometric enrollment."""

from ..domain.errors import (
    ExistingActivePersonError,
    ExistingDisabledPersonError,
    ExistingPendingPersonError,
    PersonEnrollmentCoordinationError,
)
from ..domain.models import PersonCreateRequest, PersonEnrollmentState, PersonStatus
from ..domain.ports import (
    BiometricEnrollmentWorkflowPort,
    BiometricGalleryPort,
    PeopleRepositoryPort,
    PersonRegistrationPort,
)
from ._enrollment_support import delete_pending_verified, gallery_contains
from .enrollment_session import PersonEnrollmentSession


class BeginPersonEnrollmentUseCase:
    def __init__(
        self,
        repository: PeopleRepositoryPort,
        gallery: BiometricGalleryPort,
        workflow: BiometricEnrollmentWorkflowPort,
        session: PersonEnrollmentSession,
    ) -> None:
        self._repository = repository
        self._gallery = gallery
        self._workflow = workflow
        self._session = session

    def execute(self, form: PersonRegistrationPort) -> object:
        with self._session.lock:
            self._session.require(PersonEnrollmentState.IDLE)
            self._session.state = PersonEnrollmentState.RESERVING_PERSON
            if form.cedula is None:
                self._session.state = PersonEnrollmentState.IDLE
                raise PersonEnrollmentCoordinationError("cedula is required")
            if gallery_contains(self._gallery, form.person_id):
                self._session.state = PersonEnrollmentState.IDLE
                raise PersonEnrollmentCoordinationError(
                    "person_id already exists in gallery"
                )
            existing = self._repository.get_by_cedula(form.cedula)
            if existing is not None:
                self._session.state = PersonEnrollmentState.IDLE
                if existing.status is PersonStatus.ACTIVE:
                    raise ExistingActivePersonError(existing.person_id)
                if existing.status is PersonStatus.PENDING_BIOMETRIC:
                    raise ExistingPendingPersonError(existing.person_id)
                if existing.status is PersonStatus.DISABLED:
                    raise ExistingDisabledPersonError(existing.person_id)
                raise PersonEnrollmentCoordinationError(
                    "La persona existe pero no está habilitada para enrollment."
                )
            try:
                request = PersonCreateRequest(
                    form.person_id,
                    form.cedula,
                    form.first_name,
                    form.last_name,
                    form.address,
                    form.phone,
                    form.email,
                    form.birth_date,
                    form.sex,
                    form.notes,
                )
                self._repository.create(request)
            except Exception:
                self._session.state = PersonEnrollmentState.IDLE
                raise
            self._session.reserved_person_id = form.person_id
            try:
                progress = self._workflow.start(form)
            except Exception:
                delete_pending_verified(
                    self._repository, self._session.reserved_person_id
                )
                self._session.reserved_person_id = None
                self._session.state = PersonEnrollmentState.IDLE
                raise
            self._session.state = PersonEnrollmentState.ENROLLING
            return progress
