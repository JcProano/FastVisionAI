"""Consistent SQLite snapshots using the standard backup API."""
from __future__ import annotations
import sqlite3,time
from datetime import datetime,timezone
from pathlib import Path
from .contracts import BackupIntegrityError,BackupValidationError

class SQLiteSnapshotProvider:
 def __init__(self,timeout_seconds:float=15.0):
  if timeout_seconds<=0:raise ValueError("snapshot timeout must be positive")
  self.timeout_seconds=timeout_seconds
 def create(self,source:Path,destination:Path)->tuple[int,datetime]:
  started=time.monotonic();src=dst=None
  try:
   src=sqlite3.connect(f"file:{source}?mode=ro",uri=True,timeout=self.timeout_seconds)
   dst=sqlite3.connect(destination,timeout=self.timeout_seconds)
   def progress(_status,_remaining,_total):
    if time.monotonic()-started>self.timeout_seconds:raise TimeoutError("SQLite snapshot timeout")
   src.backup(dst,pages=128,progress=progress,sleep=0.01);dst.commit()
   row=dst.execute("PRAGMA integrity_check").fetchone()
   if not row or row[0]!="ok":raise BackupIntegrityError("SQLite snapshot failed integrity check")
   tables={r[0] for r in dst.execute("SELECT name FROM sqlite_master WHERE type='table'")}
   if "schema_version" not in tables:raise BackupValidationError("SQLite schema_version is missing")
   version=dst.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
   if not isinstance(version,int) or version<1:raise BackupValidationError("SQLite schema version is invalid")
   return version,datetime.now(timezone.utc)
  finally:
   if dst is not None:dst.close()
   if src is not None:src.close()
   if 'version' not in locals():destination.unlink(missing_ok=True)
 def validate(self,path:Path,supported_version:int)->int:
  connection=sqlite3.connect(f"file:{path}?mode=ro",uri=True,timeout=self.timeout_seconds)
  try:
   row=connection.execute("PRAGMA integrity_check").fetchone()
   if not row or row[0]!="ok":raise BackupIntegrityError("SQLite file is corrupt")
   version=connection.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
   if not isinstance(version,int) or version>supported_version:raise BackupValidationError("future SQLite schema is unsupported")
   return version
  except sqlite3.Error as exc:raise BackupIntegrityError("SQLite validation failed") from exc
  finally:connection.close()
