"""In-memory ports for People application tests."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone

from src.core.people.domain import (
    PersonCreateRequest,
    PersonRecord,
    PersonSearchQuery,
    PersonStatus,
    PersonUpdateRequest,
)


class InMemoryPeopleRepository:
    def __init__(self, records: tuple[PersonRecord, ...] = ()) -> None:
        self.records = {record.person_id: record for record in records}
        self.fail_status_change = False
        self.fail_pending_delete = False
        self.created_requests: list[PersonCreateRequest] = []
        self.updated_requests: list[PersonUpdateRequest] = []
        self.search_queries: list[PersonSearchQuery] = []

    def create(self, request: PersonCreateRequest) -> PersonRecord:
        self.created_requests.append(request)
        moment = datetime(2026, 1, 2, 12, tzinfo=timezone.utc)
        record = PersonRecord(
            request.person_id,
            request.cedula,
            request.first_name,
            request.last_name,
            request.address,
            request.phone,
            request.email,
            request.birth_date,
            request.sex,
            request.notes,
            PersonStatus.PENDING_BIOMETRIC,
            moment,
            moment,
        )
        self.records[record.person_id] = record
        return record

    def get_by_person_id(self, person_id: str) -> PersonRecord | None:
        return self.records.get(person_id)

    def get_by_cedula(self, cedula: str) -> PersonRecord | None:
        return next(
            (record for record in self.records.values() if record.cedula == cedula),
            None,
        )

    def update(self, request: PersonUpdateRequest) -> PersonRecord:
        self.updated_requests.append(request)
        current = self.records[request.person_id]
        changes = {
            field: getattr(request, field)
            for field in (
                "first_name",
                "last_name",
                "address",
                "phone",
                "email",
                "birth_date",
                "sex",
                "notes",
                "cedula",
            )
            if getattr(request, field) is not None
        }
        changes.update({field: None for field in request.clear_fields})
        updated = replace(current, **changes)
        self.records[current.person_id] = updated
        return updated

    def set_status(self, person_id: str, status: PersonStatus) -> PersonRecord:
        if self.fail_status_change:
            raise RuntimeError("simulated status failure")
        updated = replace(self.records[person_id], status=status)
        self.records[person_id] = updated
        return updated

    def delete(self, person_id: str) -> bool:
        return self.records.pop(person_id, None) is not None

    def delete_pending(self, person_id: str) -> bool:
        if self.fail_pending_delete:
            raise RuntimeError("simulated pending delete failure")
        record = self.records.get(person_id)
        if record is None or record.status is not PersonStatus.PENDING_BIOMETRIC:
            return False
        del self.records[person_id]
        return True

    def search(self, query: PersonSearchQuery) -> tuple[PersonRecord, ...]:
        self.search_queries.append(query)
        records = tuple(self.records.values())
        if query.status is not None:
            records = tuple(
                record for record in records if record.status is query.status
            )
        return records[query.offset : query.offset + query.limit]


@dataclass(frozen=True)
class FakeRegistration:
    person_id: str
    cedula: str | None = "1710034065"
    first_name: str = "Temporary"
    last_name: str = "Person"
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    birth_date: str | None = None
    sex: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class FakeIdentity:
    person_id: str


class FakeGallery:
    def __init__(self) -> None:
        self.identities: set[str] = set()
        self.removal_succeeds = True

    def list_identities(self) -> tuple[FakeIdentity, ...]:
        return tuple(FakeIdentity(person_id) for person_id in self.identities)

    def templates(self, person_id: str) -> tuple[object, ...]:
        return (object(),) if person_id in self.identities else ()

    def remove_identity(self, person_id: str) -> bool:
        if not self.removal_succeeds or person_id not in self.identities:
            return False
        self.identities.remove(person_id)
        return True


@dataclass(frozen=True)
class FakeEnrollmentResult:
    enrollment_status: str
    coordination_state: str | None = None
    message: str = "biometric result"
    person_id: str = ""


class FakeEnrollmentWorkflow:
    def __init__(self, gallery: FakeGallery) -> None:
        self.gallery = gallery
        self.active = False
        self.start_error = False
        self.commit_error = False
        self.enrolled = True
        self.registration: FakeRegistration | None = None

    def start(self, registration: FakeRegistration) -> str:
        if self.start_error:
            raise RuntimeError("simulated start failure")
        self.registration = registration
        self.active = True
        return "capture-started"

    def cancel(self) -> None:
        self.active = False

    def commit_biometric(
        self, *, minimal_identity_metadata: bool = False
    ) -> FakeEnrollmentResult:
        self.active = False
        assert minimal_identity_metadata
        assert self.registration is not None
        if self.commit_error:
            raise RuntimeError("simulated commit failure")
        if self.enrolled:
            self.gallery.identities.add(self.registration.person_id)
        return FakeEnrollmentResult(
            "enrolled" if self.enrolled else "rejected",
            person_id=self.registration.person_id,
        )


class FakeEnrollmentResultEditor:
    def coordinated(
        self,
        result: FakeEnrollmentResult,
        *,
        coordination_state: str,
        message: str | None = None,
    ) -> FakeEnrollmentResult:
        changes = {"coordination_state": coordination_state}
        if message is not None:
            changes["message"] = message
        return replace(result, **changes)

    def inconsistent(
        self, person_id: str, reason: str, coordination_state: str
    ) -> FakeEnrollmentResult:
        return FakeEnrollmentResult(
            "inconsistent",
            coordination_state,
            f"{reason}; reconciliation required",
            person_id,
        )


def person_record(
    *,
    person_id: str | None = None,
    cedula: str = "1710034065",
    status: PersonStatus = PersonStatus.ACTIVE,
) -> PersonRecord:
    moment = datetime(2026, 1, 2, 12, tzinfo=timezone.utc)
    return PersonRecord(
        person_id or str(uuid.uuid4()),
        cedula,
        "Temporary",
        "Person",
        None,
        None,
        None,
        None,
        None,
        None,
        status,
        moment,
        moment,
    )
