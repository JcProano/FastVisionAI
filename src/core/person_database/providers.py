"""Compatibility exports for People identity providers."""

from src.core.people.domain.ports import IdentityDataProvider
from src.core.people.infrastructure import SQLiteIdentityDataProvider

__all__ = ["IdentityDataProvider", "SQLiteIdentityDataProvider"]
