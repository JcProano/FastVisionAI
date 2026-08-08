"""Validation and internal identifier generation for registration forms."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from src.ui.contracts import RegistrationFormData
from src.core.person_database import PersonCreateRequest, PersonDataValidationError


class RegistrationFormError(ValueError):
    pass


def validate_registration_form(
    first_name: str,
    last_name: str,
    external_identifier: str | None,
    *,
    consent_confirmed: bool,
    persist_locally: bool,
    id_factory: Callable[[], str] | None = None,
    cedula: str | None = None,
    address: str | None = None,
    phone: str | None = None,
    email: str | None = None,
    birth_date: str | None = None,
    sex: str | None = None,
    notes: str | None = None,
) -> RegistrationFormData:
    first, last, external = validate_identity_fields(
        first_name, last_name, external_identifier
    )
    if not consent_confirmed:
        raise RegistrationFormError("Se requiere consentimiento biométrico explícito")
    generated = (id_factory or (lambda: str(uuid.uuid4())))()
    if not generated.strip() or generated in {first, last, f"{first} {last}"}:
        raise RegistrationFormError("El generador produjo un person_id inválido")
    if cedula is not None:
        try:
            civil = PersonCreateRequest(
                generated, cedula, first, last, address, phone, email,
                birth_date, sex, notes,
            )
        except PersonDataValidationError as exc:
            raise RegistrationFormError(str(exc)) from exc
        generated, cedula, first, last = (
            civil.person_id, civil.cedula, civil.first_name, civil.last_name,
        )
        address, phone, email, birth_date, sex, notes = (
            civil.address, civil.phone, civil.email, civil.birth_date, civil.sex, civil.notes,
        )
    return RegistrationFormData(
        first, last, f"{first} {last}", generated, external,
        consent_confirmed, persist_locally, cedula, address, phone, email,
        birth_date, sex, notes,
    )


def validate_identity_fields(
    first_name: str, last_name: str, external_identifier: str | None,
) -> tuple[str, str, str | None]:
    return (
        _clean_required(first_name, "Nombre"),
        _clean_required(last_name, "Apellido"),
        _clean_optional(external_identifier),
    )


def _clean_required(value: str, label: str) -> str:
    cleaned = " ".join(value.strip().split())
    if not cleaned:
        raise RegistrationFormError(f"{label} no puede estar vacío")
    _validate_text(cleaned, label)
    return cleaned


def _clean_optional(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    cleaned = " ".join(value.strip().split())
    _validate_text(cleaned, "Identificador interno")
    return cleaned


def _validate_text(value: str, label: str) -> None:
    if len(value) > 120:
        raise RegistrationFormError(f"{label} excede la longitud máxima")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise RegistrationFormError(f"{label} contiene caracteres de control")
