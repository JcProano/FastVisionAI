"""Compatibility exports for People validation."""

from src.core.people.domain.errors import PersonDataValidationError
from src.core.people.domain.validators import (
    EcuadorianCedulaValidator,
    normalize_phone,
    optional_text,
    required_text,
    validate_birth_date,
    validate_email,
    validate_person_id,
)

__all__ = [name for name in globals() if not name.startswith("_")]
