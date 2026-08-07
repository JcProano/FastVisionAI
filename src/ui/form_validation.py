"""Validation and internal identifier generation for registration forms."""

from __future__ import annotations

import uuid
from collections.abc import Callable

from src.ui.contracts import RegistrationFormData


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
) -> RegistrationFormData:
    first = _clean_required(first_name, "Nombre")
    last = _clean_required(last_name, "Apellido")
    external = _clean_optional(external_identifier)
    if not consent_confirmed:
        raise RegistrationFormError("Se requiere consentimiento biométrico explícito")
    generated = (id_factory or (lambda: f"person_{uuid.uuid4().hex}"))()
    if not generated.strip() or generated in {first, last, f"{first} {last}"}:
        raise RegistrationFormError("El generador produjo un person_id inválido")
    return RegistrationFormData(
        first, last, f"{first} {last}", generated, external,
        consent_confirmed, persist_locally,
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

