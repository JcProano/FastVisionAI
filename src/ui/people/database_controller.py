"""Administrative adapter combining SQLite PII with gallery biometric statistics."""

from __future__ import annotations
from datetime import datetime, timezone

from src.core.person_database import (
    PersonRepository, PersonStatus, PersonUpdateRequest,
)

from .contracts import (
    PeopleListDTO, PeopleManagerState, PeopleOperationResultDTO, PersonDetailsDTO,
    PersonSummaryDTO,
)
from .controller import PeopleManagerController


class DatabasePeopleManagerController:
    def __init__(self, repository: PersonRepository, biometrics: PeopleManagerController) -> None:
        self.repository = repository
        self.biometrics = biometrics

    @property
    def state(self): return self.biometrics.state
    @property
    def manifest_path(self): return self.biometrics.manifest_path
    @property
    def archive_path(self): return self.biometrics.archive_path

    def list_people(self, query: str = "") -> PeopleListDTO:
        normalized = " ".join(query.casefold().split())
        records = self.repository.list(limit=1_000)
        people = tuple(
            self._summary(record) for record in records
            if not normalized or normalized in " ".join(filter(None, (
                record.cedula, record.first_name, record.last_name, record.phone, record.email,
            ))).casefold()
        )
        return PeopleListDTO(
            self.state, query, people, self.repository.count(),
            sum(item.template_count for item in people),
        )

    def details(self, person_id: str) -> PersonDetailsDTO:
        record = self.repository.get_by_person_id(person_id)
        if record is None:
            raise KeyError("unknown person_id")
        try:
            biometric = self.biometrics.details(person_id)
            profiles, versions = (biometric.quality_profile_names,
                                  biometric.quality_profile_versions)
        except Exception:
            profiles, versions = (), ()
        return PersonDetailsDTO(self._summary(record), profiles, versions)

    def update_person(
        self, person_id: str, first_name: str, last_name: str,
        external_identifier: str | None = None, *, address: str | None = None,
        phone: str | None = None, email: str | None = None,
        birth_date: str | None = None, sex: str | None = None,
        notes: str | None = None,
    ) -> PeopleOperationResultDTO:
        record = self.repository.get_by_person_id(person_id)
        if record is None:
            return self._fail("edit", "La persona no existe.", person_id)
        if external_identifier not in (None, "", record.cedula):
            return self._fail("edit", "La cédula es inmutable en esta fase.", person_id)
        try:
            optional_values = {
                "address": address, "phone": phone, "email": email,
                "birth_date": birth_date, "sex": sex, "notes": notes,
            }
            clear_fields = frozenset(
                field for field, value in optional_values.items()
                if value is not None and not value.strip()
            )
            self.repository.update(PersonUpdateRequest(
                person_id, first_name, last_name, address, phone, email,
                birth_date, sex, notes, clear_fields,
            ))
            return PeopleOperationResultDTO(
                PeopleManagerState.IDLE, True, "edit",
                "Datos civiles actualizados.", person_id,
            )
        except Exception:
            return self._fail("edit", "No se pudieron actualizar los datos civiles.", person_id)

    def delete_person(self, person_id: str, *, confirmed: bool) -> PeopleOperationResultDTO:
        return self._fail(
            "delete", "Eliminación coordinada pendiente de diseño y aprobación.", person_id,
        )

    def begin_additional(self, person_id: str) -> PeopleOperationResultDTO:
        record = self.repository.get_by_person_id(person_id)
        if record is None or record.status is not PersonStatus.ACTIVE:
            return self._fail(
                "additional_start", "Solo personas civiles ACTIVE admiten muestras adicionales.",
                person_id,
            )
        return self.biometrics.begin_additional(person_id)

    def set_administrative_status(
        self, person_id: str, target: PersonStatus, *, confirmed: bool,
    ) -> PeopleOperationResultDTO:
        moment = datetime.now(timezone.utc)
        if not confirmed:
            return PeopleOperationResultDTO(
                PeopleManagerState.IDLE, False, "status_change",
                "Cambio de estado cancelado.", person_id, timestamp=moment,
            )
        try:
            current = self.repository.get_by_person_id(person_id)
            if current is None:
                return PeopleOperationResultDTO(
                    PeopleManagerState.ERROR, False, "status_change",
                    "La persona no existe.", person_id, timestamp=moment,
                )
            allowed = {
                (PersonStatus.ACTIVE, PersonStatus.DISABLED),
                (PersonStatus.DISABLED, PersonStatus.ACTIVE),
            }
            if (current.status, target) not in allowed:
                return PeopleOperationResultDTO(
                    PeopleManagerState.ERROR, False, "status_change",
                    "La transición administrativa no está permitida.", person_id,
                    timestamp=moment,
                )
            self.repository.set_status(person_id, target)
            return PeopleOperationResultDTO(
                PeopleManagerState.IDLE, True, "status_change",
                "Estado administrativo actualizado.", person_id, timestamp=moment,
            )
        except Exception:
            return PeopleOperationResultDTO(
                PeopleManagerState.ERROR, False, "status_change",
                "No se pudo actualizar el estado administrativo.", person_id,
                timestamp=moment,
            )

    def __getattr__(self, name: str):
        return getattr(self.biometrics, name)

    def _summary(self, record) -> PersonSummaryDTO:
        try:
            biometric = self.biometrics.details(record.person_id).summary
            template_count = biometric.template_count
            scored = biometric.scored_template_count
            unscored = biometric.unscored_template_count
            average, minimum, maximum = (biometric.average_quality,
                                         biometric.minimum_quality,
                                         biometric.maximum_quality)
            created = biometric.created_at
        except Exception:
            template_count = scored = unscored = 0
            average = minimum = maximum = created = None
        return PersonSummaryDTO(
            record.person_id, record.first_name, record.last_name,
            f"{record.first_name} {record.last_name}", record.cedula,
            template_count, scored, unscored, average, minimum, maximum, created,
            record.cedula, record.address, record.phone, record.email,
            record.birth_date, record.sex, record.notes, record.status.value,
        )

    @staticmethod
    def _fail(operation: str, message: str, person_id: str) -> PeopleOperationResultDTO:
        return PeopleOperationResultDTO(
            PeopleManagerState.ERROR, False, operation, message, person_id,
        )
