"""Version-one schema for the independent detection-event database."""
from __future__ import annotations
import sqlite3
from .contracts import DetectionEventRepositoryError

SCHEMA_VERSION = 1


def initialize_schema(connection: sqlite3.Connection) -> int:
    connection.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
    row = connection.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
    if row is not None and int(row[0]) > SCHEMA_VERSION:
        raise DetectionEventRepositoryError("event database schema is newer than supported")
    if row is None:
        connection.execute("INSERT INTO schema_version(version) VALUES (?)", (SCHEMA_VERSION,))
    connection.execute("""
        CREATE TABLE IF NOT EXISTS detection_events (
            event_id TEXT PRIMARY KEY,
            person_id TEXT,
            event_type TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            camera_id TEXT,
            display_name_snapshot TEXT,
            similarity REAL,
            quality_score REAL,
            recognition_state TEXT NOT NULL,
            administrative_status TEXT,
            session_id TEXT,
            created_at TEXT NOT NULL
        )
    """)
    connection.execute("CREATE INDEX IF NOT EXISTS idx_events_time ON detection_events(timestamp)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_events_person ON detection_events(person_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_events_type ON detection_events(event_type)")
    return SCHEMA_VERSION

