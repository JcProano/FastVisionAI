"""Ports owned by the People bounded context."""

from __future__ import annotations

from typing import Protocol

from .models import (
    PersonCreateRequest,
    PersonRecord,
    PersonSearchQuery,
    PersonStatus,
    PersonUpdateRequest,
)


class PeopleRepositoryPort(Protocol):
    def create(self, request: PersonCreateRequest) -> PersonRecord: ...
    def get_by_person_id(self, person_id: str) -> PersonRecord | None: ...
    def get_by_cedula(self, cedula: str) -> PersonRecord | None: ...
    def update(self, request: PersonUpdateRequest) -> PersonRecord: ...
    def set_status(self, person_id: str, status: PersonStatus) -> PersonRecord: ...
    def delete(self, person_id: str) -> bool: ...
    def delete_pending(self, person_id: str) -> bool: ...
    def search(self, query: PersonSearchQuery) -> tuple[PersonRecord, ...]: ...


class IdentityDataProvider(Protocol):
    def get_by_person_id(self, person_id: str) -> PersonRecord | None: ...
    def get_by_cedula(self, cedula: str) -> PersonRecord | None: ...
    def search(self, query: PersonSearchQuery) -> tuple[PersonRecord, ...]: ...


class PersonRegistrationPort(Protocol):
    person_id: str
    cedula: str | None
    first_name: str
    last_name: str
    address: str | None
    phone: str | None
    email: str | None
    birth_date: str | None
    sex: str | None
    notes: str | None


class BiometricIdentityPort(Protocol):
    person_id: str


class BiometricGalleryPort(Protocol):
    def list_identities(self) -> tuple[BiometricIdentityPort, ...]: ...
    def templates(self, person_id: str) -> tuple[object, ...]: ...
    def remove_identity(self, person_id: str) -> bool: ...


class EnrollmentResultPort(Protocol):
    enrollment_status: str


class BiometricEnrollmentWorkflowPort(Protocol):
    @property
    def active(self) -> bool: ...

    def start(self, registration: PersonRegistrationPort) -> object: ...
    def cancel(self) -> None: ...
    def commit_biometric(
        self, *, minimal_identity_metadata: bool = False
    ) -> EnrollmentResultPort: ...


class EnrollmentResultEditorPort(Protocol):
    def coordinated(
        self,
        result: EnrollmentResultPort,
        *,
        coordination_state: str,
        message: str | None = None,
    ) -> EnrollmentResultPort: ...

    def inconsistent(
        self, person_id: str, reason: str, coordination_state: str
    ) -> EnrollmentResultPort: ...
