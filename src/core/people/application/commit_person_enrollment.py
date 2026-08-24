"""Use case for activating a person after an atomic biometric commit."""

from __future__ import annotations

from typing import Callable

from ..domain.errors import PersonEnrollmentCoordinationError
from ..domain.models import PersonEnrollmentState, PersonStatus
from ..domain.ports import (
    BiometricEnrollmentWorkflowPort,
    BiometricGalleryPort,
    EnrollmentResultEditorPort,
    EnrollmentResultPort,
    PeopleRepositoryPort,
)
from ._enrollment_support import delete_pending_verified, gallery_contains
from .enrollment_session import PersonEnrollmentSession


class CommitPersonEnrollmentUseCase:
    def __init__(
        self,
        repository: PeopleRepositoryPort,
        gallery: BiometricGalleryPort,
        workflow: BiometricEnrollmentWorkflowPort,
        results: EnrollmentResultEditorPort,
        session: PersonEnrollmentSession,
        audit_callback: Callable[[str, dict[str, str]], None] | None = None,
    ) -> None:
        self._repository = repository
        self._gallery = gallery
        self._workflow = workflow
        self._results = results
        self._session = session
        self._audit_callback = audit_callback

    def execute(self) -> EnrollmentResultPort:
        with self._session.lock:
            self._session.require(PersonEnrollmentState.ENROLLING)
            person_id = self._session.reserved_person_id
            if person_id is None:
                raise PersonEnrollmentCoordinationError("reservation is missing")
            try:
                result = self._workflow.commit_biometric(
                    minimal_identity_metadata=True
                )
            except Exception:
                if gallery_contains(self._gallery, person_id):
                    return self._compensate(person_id, "biometric commit failed")
                delete_pending_verified(self._repository, person_id)
                self._session.reserved_person_id = None
                self._session.state = PersonEnrollmentState.IDLE
                raise
            if result.enrollment_status.casefold() != "enrolled":
                delete_pending_verified(self._repository, person_id)
                self._session.reserved_person_id = None
                self._session.state = PersonEnrollmentState.IDLE
                return self._results.coordinated(
                    result,
                    coordination_state=self._session.state.value,
                )
            self._session.state = PersonEnrollmentState.ACTIVATING_PERSON
            try:
                self._repository.set_status(person_id, PersonStatus.ACTIVE)
            except Exception:
                pass
            try:
                record = self._repository.get_by_person_id(person_id)
            except Exception:
                record = None
            if record is None or record.status is not PersonStatus.ACTIVE:
                return self._compensate(person_id, "civil activation failed")
            self._session.reserved_person_id = None
            self._session.state = PersonEnrollmentState.ACTIVE
            completed = self._results.coordinated(
                result,
                coordination_state=self._session.state.value,
                message="Registro biométrico y civil activo",
            )
            self._session.state = PersonEnrollmentState.IDLE
            self._audit("PERSON_CREATED", {"person_id": person_id})
            return completed

    def _compensate(
        self, person_id: str, reason: str
    ) -> EnrollmentResultPort:
        self._session.state = PersonEnrollmentState.ROLLING_BACK
        try:
            removed = self._gallery.remove_identity(person_id)
            gallery_clean = removed and not gallery_contains(
                self._gallery, person_id
            )
        except Exception:
            gallery_clean = False
        if not gallery_clean:
            self._session.state = PersonEnrollmentState.INCONSISTENT
            return self._results.inconsistent(
                person_id, reason, self._session.state.value
            )
        try:
            pending_removed = self._repository.delete_pending(person_id)
            database_clean = (
                pending_removed
                and self._repository.get_by_person_id(person_id) is None
            )
        except Exception:
            database_clean = False
        if not database_clean:
            self._session.state = PersonEnrollmentState.INCONSISTENT
            return self._results.inconsistent(
                person_id, reason, self._session.state.value
            )
        self._session.reserved_person_id = None
        self._session.state = PersonEnrollmentState.IDLE
        raise PersonEnrollmentCoordinationError(
            f"{reason}; compensation completed"
        )

    def _audit(self, event: str, payload: dict[str, str]) -> None:
        if self._audit_callback:
            try:
                self._audit_callback(event, payload)
            except Exception:
                pass
