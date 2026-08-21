"""Compatibility exports for the SQLite security repository."""

from .domain.models import LastActiveAdminError
from .infrastructure import SQLiteUserRepository

UserRepository = SQLiteUserRepository

__all__ = ["LastActiveAdminError", "UserRepository"]
