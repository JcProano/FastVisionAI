from __future__ import annotations
import sqlite3,tempfile,unittest
from pathlib import Path
from src.core.backup import BackupArchive,BackupRequest,BackupService,BackupSourceCatalog,SQLiteSnapshotProvider
from src.core.system_health import HealthLevel,SQLiteDatabaseHealthProvider

class BackupHealthSmokeTests(unittest.TestCase):
 def test_audit_database_snapshot_verify_and_read_only_health(self):
  with tempfile.TemporaryDirectory() as name:
   root=Path(name);audit=root/"state/audit.db";audit.parent.mkdir()
   with sqlite3.connect(audit) as connection:connection.execute("CREATE TABLE schema_version(version INTEGER NOT NULL)");connection.execute("INSERT INTO schema_version VALUES(1)")
   settings={"audit":{"database_path":"state/audit.db"},"backup":{"include_configuration":False},"thumbnails":{"directory":"thumbs"}}
   service=BackupService(BackupSourceCatalog(root,settings),BackupArchive(),SQLiteSnapshotProvider());target=root/"backup.fvbackup";service.create(BackupRequest(target));verified=service.verify(target);self.assertTrue(verified.valid)
   manifest,_=BackupArchive().verify(target);entry=next(item for item in manifest.files if item.component_type.value=="AUDIT_DATABASE");self.assertEqual(entry.schema_version,1)
   self.assertEqual(SQLiteDatabaseHealthProvider("audit_database",audit).check().level,HealthLevel.OK)

