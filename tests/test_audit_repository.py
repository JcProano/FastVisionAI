from __future__ import annotations
import tempfile,unittest,sqlite3
from datetime import datetime,timezone
from pathlib import Path
from src.core.audit import *

def record(identifier="1",action=AuditAction.LOGIN_SUCCESS,success=True):
 return AuditRecord(identifier,datetime.now(timezone.utc),"actor","ADMIN",action,AuditEntityType.SESSION,None,success,"safe","test","session",{})

class AuditRepositoryTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.repo=AuditRepository(Path(self.temp.name)/"audit.db");self.assertEqual(self.repo.initialize(),1)
 def tearDown(self):self.temp.cleanup()
 def test_append_and_query(self):
  self.repo.append(record());rows=self.repo.query(AuditQuery());self.assertEqual(rows[0].audit_id,"1")
 def test_append_only_surface(self):
  self.assertFalse(hasattr(self.repo,"update"));self.assertFalse(hasattr(self.repo,"delete"));self.assertFalse(hasattr(self.repo,"purge"))
 def test_filters_and_summary(self):
  self.repo.append(record("1"));self.repo.append(record("2",AuditAction.LOGIN_FAILURE,False));rows=self.repo.query(AuditQuery(success=False));self.assertEqual(len(rows),1);summary=self.repo.summary();self.assertEqual((summary.total,summary.successes,summary.failures),(2,1,1))
 def test_future_schema_rejected(self):
  path=Path(self.temp.name)/"future.db";connection=sqlite3.connect(path);connection.execute("CREATE TABLE schema_version(version INTEGER NOT NULL)");connection.execute("INSERT INTO schema_version VALUES(99)");connection.commit();connection.close()
  with self.assertRaises(AuditRepositoryError):AuditRepository(path).initialize()
 def test_duplicate_id_rolls_back(self):
  self.repo.append(record())
  with self.assertRaises(AuditRepositoryError):self.repo.append(record())
  self.assertEqual(self.repo.summary().total,1)

