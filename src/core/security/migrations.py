from __future__ import annotations
import sqlite3
from datetime import datetime, timezone
SCHEMA_VERSION=1
class SecurityMigrationError(RuntimeError): pass
def initialize_schema(connection:sqlite3.Connection)->int:
    tables={r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
    if not tables:
        connection.execute("CREATE TABLE schema_version(version INTEGER PRIMARY KEY,applied_at TEXT NOT NULL)")
        connection.execute("""CREATE TABLE users(user_id TEXT PRIMARY KEY,username TEXT NOT NULL UNIQUE COLLATE NOCASE,display_name TEXT NOT NULL,password_hash BLOB NOT NULL,password_salt BLOB NOT NULL,password_algorithm TEXT NOT NULL,password_parameters TEXT NOT NULL,role TEXT NOT NULL,status TEXT NOT NULL,failed_attempts INTEGER NOT NULL DEFAULT 0,locked_until TEXT,last_login_at TEXT,password_changed_at TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)""")
        connection.execute("INSERT INTO schema_version VALUES(?,?)",(1,datetime.now(timezone.utc).isoformat())); return 1
    if "schema_version" not in tables or "users" not in tables: raise SecurityMigrationError("users database schema is invalid")
    version=connection.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
    if version != 1: raise SecurityMigrationError("users database schema version is unsupported")
    return 1
