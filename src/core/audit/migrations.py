"""Schema migration for the independent administrative audit database."""
from __future__ import annotations
import sqlite3
from .contracts import AuditRepositoryError

SCHEMA_VERSION = 1

def initialize_schema(connection: sqlite3.Connection) -> int:
    connection.execute("CREATE TABLE IF NOT EXISTS schema_version(version INTEGER NOT NULL)")
    row = connection.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
    if row is not None and int(row[0]) > SCHEMA_VERSION:
        raise AuditRepositoryError("audit database schema is newer than supported")
    if row is None:
        connection.execute("INSERT INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION,))
    connection.execute("""CREATE TABLE IF NOT EXISTS audit_records(
        audit_id TEXT PRIMARY KEY,
        timestamp_utc TEXT NOT NULL,
        actor_user_id TEXT,
        actor_role TEXT,
        action TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        entity_id TEXT,
        success INTEGER NOT NULL CHECK(success IN (0,1)),
        message TEXT NOT NULL,
        source TEXT NOT NULL,
        session_id TEXT,
        metadata_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL
    )""")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_records(timestamp_utc DESC)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_records(action)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_records(actor_user_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_records(entity_type,entity_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_audit_success ON audit_records(success)")
    return SCHEMA_VERSION

