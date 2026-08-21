"""Explicit version-one SQLite schema; unknown future versions are rejected."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

SCHEMA_VERSION = 1


class PersonDatabaseMigrationError(RuntimeError):
    pass


def initialize_schema(connection: sqlite3.Connection) -> int:
    tables = {
        str(row[0]) for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = ? AND name NOT LIKE ?",
            ("table", "sqlite_%"),
        )
    }
    if "schema_version" not in tables:
        if tables:
            raise PersonDatabaseMigrationError("database contains an unversioned schema")
        _create_version_one(connection)
        return SCHEMA_VERSION
    row = connection.execute("SELECT MAX(version) FROM schema_version").fetchone()
    if row is None or row[0] is None:
        raise PersonDatabaseMigrationError("schema version is missing")
    version = int(row[0])
    if version > SCHEMA_VERSION:
        raise PersonDatabaseMigrationError("database schema version is newer than supported")
    if version < SCHEMA_VERSION:
        raise PersonDatabaseMigrationError("database schema requires an explicit migration")
    if "people" not in tables:
        raise PersonDatabaseMigrationError("versioned database is missing the people table")
    return version


def _create_version_one(connection: sqlite3.Connection) -> None:
    try:
        connection.execute("BEGIN")
        connection.execute(
            "CREATE TABLE schema_version (version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        connection.execute(
            """CREATE TABLE people (
                person_id TEXT PRIMARY KEY,
                cedula TEXT NOT NULL UNIQUE,
                first_name TEXT NOT NULL,
                last_name TEXT NOT NULL,
                address TEXT,
                phone TEXT,
                email TEXT,
                birth_date TEXT,
                sex TEXT,
                notes TEXT,
                status TEXT NOT NULL CHECK (
                    status IN ('PENDING_BIOMETRIC', 'ACTIVE', 'DISABLED')
                ),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )
        connection.execute("CREATE INDEX idx_people_first_name ON people(first_name COLLATE NOCASE)")
        connection.execute("CREATE INDEX idx_people_last_name ON people(last_name COLLATE NOCASE)")
        connection.execute("CREATE INDEX idx_people_phone ON people(phone)")
        connection.execute("CREATE INDEX idx_people_email ON people(email COLLATE NOCASE)")
        connection.execute("CREATE INDEX idx_people_status ON people(status)")
        connection.execute(
            "INSERT INTO schema_version(version, applied_at) VALUES (?, ?)",
            (SCHEMA_VERSION, datetime.now(timezone.utc).isoformat()),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
