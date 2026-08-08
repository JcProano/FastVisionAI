"""Read-oriented composition boundary for civil and safe biometric profile data."""

from __future__ import annotations

from src.core.person_database import PersonRepository, PersonStatus
from src.ui.people.controller import PeopleManagerController
from src.ui.people.database_controller import DatabasePeopleManagerController
from src.ui.thumbnails import ThumbnailManager

from .contracts import PersonProfileDTO, PersonProfileOperationDTO, PersonProfileStatus
from src.ui.attendance import AttendanceUIController


_MESSAGES = {
    PersonProfileStatus.ACTIVE: "Persona registrada con estado administrativo ACTIVE",
    PersonProfileStatus.DISABLED: "Registro administrativo deshabilitado",
    PersonProfileStatus.PENDING_BIOMETRIC: "Registro pendiente de completar",
    PersonProfileStatus.LEGACY_BIOMETRIC_ONLY:
        "Registro biométrico heredado sin datos civiles",
    PersonProfileStatus.NOT_FOUND: "No se encontró la persona solicitada",
}


class PersonProfileController:
    def __init__(
        self, repository: PersonRepository,
        administration: DatabasePeopleManagerController,
        biometrics: PeopleManagerController, thumbnails: ThumbnailManager,
        attendance: AttendanceUIController | None = None,
    ) -> None:
        self._repository = repository
        self._administration = administration
        self._biometrics = biometrics
        self._thumbnails = thumbnails
        self._attendance = attendance

    def get_by_cedula(self, cedula: str) -> PersonProfileDTO:
        record = self._repository.get_by_cedula(cedula)
        return self.get_by_person_id(record.person_id) if record else self._not_found(None)

    def get_by_person_id(self, person_id: str) -> PersonProfileDTO:
        record = self._repository.get_by_person_id(person_id)
        identity = next(
            (item for item in self._biometrics.gallery.list_identities()
             if item.person_id == person_id), None,
        )
        if record is None and identity is None:
            return self._not_found(person_id)
        status = (
            PersonProfileStatus.LEGACY_BIOMETRIC_ONLY if record is None
            else PersonProfileStatus(record.status.value)
        )
        summary = None
        try:
            summary = self._biometrics.details(person_id).summary
        except KeyError:
            pass
        template_refs = self._biometrics.gallery.templates(person_id)
        dates = tuple(item.template.created_at for item in template_refs)
        try:
            thumbnail = self._thumbnails.load(person_id)
        except Exception:
            thumbnail = None
        attendance = None
        if self._attendance is not None and record is not None:
            try:
                attendance = self._attendance.person_summary(person_id)
            except Exception:
                # Attendance is an optional projection; profile data remains available.
                attendance = None
        return PersonProfileDTO(
            person_id,
            None if record is None else record.cedula,
            None if record is None else record.first_name,
            None if record is None else record.last_name,
            identity.display_name if record is None and identity is not None else
                (None if record is None else f"{record.first_name} {record.last_name}"),
            None if record is None else record.address,
            None if record is None else record.phone,
            None if record is None else record.email,
            None if record is None else record.birth_date,
            None if record is None else record.sex,
            None if record is None else record.notes,
            status,
            None if record is None else record.created_at,
            None if record is None else record.updated_at,
            bool(thumbnail and thumbnail.available),
            thumbnail.image_bytes if thumbnail and thumbnail.available else None,
            len(template_refs), 0 if summary is None else summary.scored_template_count,
            None if summary is None else summary.average_quality,
            None if summary is None else summary.minimum_quality,
            None if summary is None else summary.maximum_quality,
            min(dates) if dates else None, max(dates) if dates else None,
            record is None, _MESSAGES[status],
            None if attendance is None else attendance.last_check_in,
            None if attendance is None else attendance.last_check_out,
            0 if attendance is None else attendance.events_today,
        )

    def update_person(
        self, person_id: str, *, first_name: str, last_name: str,
        address: str | None = None, phone: str | None = None,
        email: str | None = None, birth_date: str | None = None,
        sex: str | None = None, notes: str | None = None,
    ) -> PersonProfileOperationDTO:
        current = self._repository.get_by_person_id(person_id)
        if current is None:
            return PersonProfileOperationDTO(False, "edit", "La persona no existe.")
        result = self._administration.update_person(
            person_id, first_name, last_name, current.cedula,
            address=address, phone=phone, email=email, birth_date=birth_date,
            sex=sex, notes=notes,
        )
        return PersonProfileOperationDTO(
            result.success, "edit", result.message,
            self.get_by_person_id(person_id) if result.success else None,
        )

    def begin_additional(self, person_id: str) -> PersonProfileOperationDTO:
        profile = self.get_by_person_id(person_id)
        if profile.administrative_status is not PersonProfileStatus.ACTIVE:
            return PersonProfileOperationDTO(
                False, "additional_start",
                "Solo una persona ACTIVE admite muestras adicionales.", profile,
            )
        return PersonProfileOperationDTO(
            True, "additional_start", "Captura adicional disponible.", profile,
        )

    def manual_attendance(self, person_id: str, *, check_in: bool):
        if self._attendance is None:
            return None
        return (self._attendance.manual_check_in(person_id) if check_in
                else self._attendance.manual_check_out(person_id))

    def _not_found(self, person_id: str | None) -> PersonProfileDTO:
        return PersonProfileDTO(
            person_id, None, None, None, None, None, None, None, None, None, None,
            PersonProfileStatus.NOT_FOUND, None, None, False, None, 0, 0,
            None, None, None, None, None, False,
            _MESSAGES[PersonProfileStatus.NOT_FOUND],
        )
