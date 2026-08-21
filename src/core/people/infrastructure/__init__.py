"""People persistence and local identity adapters."""

from .migrations import SCHEMA_VERSION, PersonDatabaseMigrationError
from .providers import SQLiteIdentityDataProvider
from .sqlite_repository import SQLitePeopleRepository

__all__ = [
    "PersonDatabaseMigrationError",
    "SCHEMA_VERSION",
    "SQLiteIdentityDataProvider",
    "SQLitePeopleRepository",
]
