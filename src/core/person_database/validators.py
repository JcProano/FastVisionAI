"""Deterministic validation for local administrative person data."""

from __future__ import annotations

import re
import uuid
from datetime import date


class PersonDataValidationError(ValueError):
    """Safe validation failure that never asserts real-world identity."""


class EcuadorianCedulaValidator:
    COEFFICIENTS = (2, 1, 2, 1, 2, 1, 2, 1, 2)

    @classmethod
    def validate(cls, value: str) -> str:
        if not isinstance(value, str) or not value.isascii() or not value.isdigit():
            raise PersonDataValidationError("cedula must contain exactly 10 ASCII digits")
        if len(value) != 10:
            raise PersonDataValidationError("cedula must contain exactly 10 digits")
        province = int(value[:2])
        if not 1 <= province <= 24:
            raise PersonDataValidationError("cedula province code is invalid")
        if int(value[2]) > 5:
            raise PersonDataValidationError("cedula third digit is invalid for a natural person")
        total = 0
        for digit, coefficient in zip(map(int, value[:9]), cls.COEFFICIENTS):
            product = digit * coefficient
            total += product - 9 if product > 9 else product
        expected = (10 - total % 10) % 10
        if expected != int(value[9]):
            raise PersonDataValidationError("cedula checksum is invalid")
        return value

    @classmethod
    def is_valid(cls, value: str) -> bool:
        try:
            cls.validate(value)
        except PersonDataValidationError:
            return False
        return True


def validate_person_id(value: str) -> str:
    cleaned = value.strip()
    try:
        parsed = uuid.UUID(cleaned)
    except (ValueError, AttributeError) as exc:
        raise PersonDataValidationError("person_id must be a valid UUID") from exc
    if str(parsed) != cleaned.casefold():
        raise PersonDataValidationError("person_id must use canonical UUID format")
    return str(parsed)


def required_text(value: str, field: str, maximum: int = 120) -> str:
    cleaned = " ".join(value.strip().split())
    if not cleaned:
        raise PersonDataValidationError(f"{field} is required")
    return _safe_text(cleaned, field, maximum)


def optional_text(value: str | None, field: str, maximum: int = 500) -> str | None:
    if value is None or not value.strip():
        return None
    return _safe_text(" ".join(value.strip().split()), field, maximum)


def validate_email(value: str | None) -> str | None:
    cleaned = optional_text(value, "email", 254)
    if cleaned is None:
        return None
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", cleaned):
        raise PersonDataValidationError("email syntax is invalid")
    local, domain = cleaned.rsplit("@", 1)
    return f"{local}@{domain.casefold()}"


def normalize_phone(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    raw = value.strip()
    if any(character not in "+0123456789 ()-." for character in raw):
        raise PersonDataValidationError("phone contains unsupported characters")
    plus = raw.startswith("+")
    digits = "".join(character for character in raw if character.isdigit())
    if not 7 <= len(digits) <= 15:
        raise PersonDataValidationError("phone must contain between 7 and 15 digits")
    return ("+" if plus else "") + digits


def validate_birth_date(value: str | None, *, today: date | None = None) -> str | None:
    if value is None or not value.strip():
        return None
    cleaned = value.strip()
    try:
        parsed = date.fromisoformat(cleaned)
    except ValueError as exc:
        raise PersonDataValidationError("birth_date must use YYYY-MM-DD") from exc
    if parsed.isoformat() != cleaned:
        raise PersonDataValidationError("birth_date must use YYYY-MM-DD")
    if parsed > (today or date.today()):
        raise PersonDataValidationError("birth_date cannot be in the future")
    return cleaned


def _safe_text(value: str, field: str, maximum: int) -> str:
    if len(value) > maximum:
        raise PersonDataValidationError(f"{field} exceeds maximum length")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise PersonDataValidationError(f"{field} contains control characters")
    return value
