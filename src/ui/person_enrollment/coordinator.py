"""Single application boundary coordinating civil reservation and biometric commit."""

from __future__ import annotations

import threading
from dataclasses import replace

from src.core.person_database import (
    PersonCreateRequest, PersonRepository, PersonStatus,
)
from src.engine.gallery import FaceGallery
from src.ui.contracts import (
    EnrollmentProgressDTO, EnrollmentResultDTO, RegistrationFormData, UIState,
)
from src.ui.enrollment_workflow import LocalEnrollmentWorkflow

from .contracts import (
    ExistingActivePersonError, ExistingPendingPersonError,
    PersonEnrollmentCoordinationError, PersonEnrollmentState,
)


class PersonEnrollmentCoordinator:
    def __init__(self, repository: PersonRepository, gallery: FaceGallery,
                 workflow: LocalEnrollmentWorkflow, audit_callback=None) -> None:
        self.repository = repository
        self.gallery = gallery
        self.workflow = workflow
        self._state = PersonEnrollmentState.IDLE
        self._reserved_person_id: str | None = None
        self._lock = threading.RLock()
        self.audit_callback = audit_callback

    @property
    def state(self) -> PersonEnrollmentState:
        return self._state

    @property
    def active(self) -> bool:
        return self.workflow.active

    def begin(self, form: RegistrationFormData) -> EnrollmentProgressDTO:
        with self._lock:
            self._require(PersonEnrollmentState.IDLE)
            self._state = PersonEnrollmentState.RESERVING_PERSON
            if form.cedula is None:
                self._state = PersonEnrollmentState.IDLE
                raise PersonEnrollmentCoordinationError("cedula is required")
            if any(item.person_id == form.person_id for item in self.gallery.list_identities()):
                self._state = PersonEnrollmentState.IDLE
                raise PersonEnrollmentCoordinationError("person_id already exists in gallery")
            existing = self.repository.get_by_cedula(form.cedula)
            if existing is not None:
                self._state = PersonEnrollmentState.IDLE
                if existing.status is PersonStatus.ACTIVE:
                    raise ExistingActivePersonError(existing.person_id)
                if existing.status is PersonStatus.PENDING_BIOMETRIC:
                    raise ExistingPendingPersonError(existing.person_id)
                raise PersonEnrollmentCoordinationError(
                    "La persona existe pero no está habilitada para enrollment."
                )
            try:
                request = PersonCreateRequest(
                    form.person_id, form.cedula, form.first_name, form.last_name,
                    form.address, form.phone, form.email, form.birth_date, form.sex, form.notes,
                )
                self.repository.create(request)
            except Exception:
                self._state = PersonEnrollmentState.IDLE
                raise
            self._reserved_person_id = form.person_id
            try:
                progress = self.workflow.start(form)
            except Exception:
                self._delete_reservation_verified()
                self._state = PersonEnrollmentState.IDLE
                raise
            self._state = PersonEnrollmentState.ENROLLING
            return progress

    def cancel(self) -> None:
        with self._lock:
            if self.workflow.active:
                self.workflow.cancel()
            if self._reserved_person_id is not None:
                self._delete_reservation_verified()
            self._reserved_person_id = None
            self._state = PersonEnrollmentState.IDLE

    def commit(self) -> EnrollmentResultDTO:
        with self._lock:
            self._require(PersonEnrollmentState.ENROLLING)
            person_id = self._reserved_person_id
            if person_id is None:
                raise PersonEnrollmentCoordinationError("reservation is missing")
            try:
                result = self.workflow.commit_biometric(minimal_identity_metadata=True)
            except Exception:
                if self._gallery_contains(person_id):
                    return self._compensate(person_id, "biometric commit failed")
                self._delete_reservation_verified()
                self._reserved_person_id = None
                self._state = PersonEnrollmentState.IDLE
                raise
            if result.enrollment_status.casefold() != "enrolled":
                self._delete_reservation_verified()
                self._reserved_person_id = None
                self._state = PersonEnrollmentState.IDLE
                return replace(result, coordination_state=self._state.value)
            self._state = PersonEnrollmentState.ACTIVATING_PERSON
            try:
                self.repository.set_status(person_id, PersonStatus.ACTIVE)
            except Exception:
                pass
            try:
                record = self.repository.get_by_person_id(person_id)
            except Exception:
                record = None
            if record is None or record.status is not PersonStatus.ACTIVE:
                return self._compensate(person_id, "civil activation failed")
            self._reserved_person_id = None
            self._state = PersonEnrollmentState.ACTIVE
            completed = replace(
                result, coordination_state=self._state.value,
                message="Registro biométrico y civil activo",
            )
            self._state = PersonEnrollmentState.IDLE
            self._audit("PERSON_CREATED", {"person_id": person_id})
            return completed

    def _audit(self, event: str, payload: dict[str, str]) -> None:
        if self.audit_callback:
            try: self.audit_callback(event, payload)
            except Exception: pass

    def _compensate(self, person_id: str, reason: str) -> EnrollmentResultDTO:
        self._state = PersonEnrollmentState.ROLLING_BACK
        try:
            removed = self.gallery.remove_identity(person_id)
            gallery_clean = removed and not self._gallery_contains(person_id)
        except Exception:
            gallery_clean = False
        if not gallery_clean:
            self._state = PersonEnrollmentState.INCONSISTENT
            return _inconsistent(person_id, reason)
        try:
            pending_removed = self.repository.delete_pending(person_id)
            database_clean = pending_removed and self.repository.get_by_person_id(person_id) is None
        except Exception:
            database_clean = False
        if not database_clean:
            self._state = PersonEnrollmentState.INCONSISTENT
            return _inconsistent(person_id, reason)
        self._reserved_person_id = None
        self._state = PersonEnrollmentState.IDLE
        raise PersonEnrollmentCoordinationError(f"{reason}; compensation completed")

    def _delete_reservation_verified(self) -> None:
        person_id = self._reserved_person_id
        if person_id is None:
            return
        if not self.repository.delete_pending(person_id):
            raise PersonEnrollmentCoordinationError("pending reservation could not be removed")
        if self.repository.get_by_person_id(person_id) is not None:
            raise PersonEnrollmentCoordinationError("pending reservation removal was not verified")

    def _gallery_contains(self, person_id: str) -> bool:
        return any(item.person_id == person_id for item in self.gallery.list_identities()) or bool(
            self.gallery.templates(person_id)
        )

    def _require(self, expected: PersonEnrollmentState) -> None:
        if self._state is not expected:
            raise PersonEnrollmentCoordinationError(
                f"invalid coordinator transition from {self._state.value}"
            )


def _inconsistent(person_id: str, reason: str) -> EnrollmentResultDTO:
    return EnrollmentResultDTO(
        state=UIState.ERROR,
        person_id=person_id, first_name="", last_name="", display_name="",
        templates_registered=0, templates_rejected=0, average_quality=0,
        minimum_quality=0, maximum_quality=0, enrollment_status="inconsistent",
        persistence_requested=False, persistence_succeeded=None,
        message=f"{reason}; reconciliación administrativa requerida",
        coordination_state=PersonEnrollmentState.INCONSISTENT.value,
    )
