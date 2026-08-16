import sqlite3
from .contracts import AttendanceRepositoryError
SCHEMA_VERSION=2
def initialize_schema(connection:sqlite3.Connection)->int:
    connection.execute("CREATE TABLE IF NOT EXISTS schema_version(version INTEGER NOT NULL)")
    row=connection.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
    if row and int(row[0])>SCHEMA_VERSION: raise AttendanceRepositoryError("attendance schema newer than supported")
    if row is None: connection.execute("INSERT INTO schema_version(version) VALUES (?)",(1,))
    connection.execute("""CREATE TABLE IF NOT EXISTS attendance_records(
      attendance_id TEXT PRIMARY KEY, person_id TEXT NOT NULL,event_type TEXT NOT NULL,
      timestamp TEXT NOT NULL,source_event_id TEXT,camera_id TEXT,session_id TEXT,
      created_at TEXT NOT NULL,notes TEXT)""")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_attendance_person ON attendance_records(person_id)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_attendance_time ON attendance_records(timestamp)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_attendance_type ON attendance_records(event_type)")
    current = 1 if row is None else int(row[0])
    if current < 2:
        connection.execute("""CREATE TABLE attendance_consumed_events(
          source_event_id TEXT PRIMARY KEY, attendance_id TEXT, consumed_at TEXT NOT NULL)""")
        connection.execute("UPDATE schema_version SET version=2")
        current = 2
    return current
