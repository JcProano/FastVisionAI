from __future__ import annotations
import tempfile,unittest
from pathlib import Path
from src.core.audit import *

class AuditServiceTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.repo=AuditRepository(Path(self.temp.name)/"audit.db");self.repo.initialize();self.service=AuditService(self.repo)
 def tearDown(self):self.temp.cleanup()
 def test_record(self):
  result=self.service.safe_record(AuditAction.REPORT_EXPORTED,AuditEntityType.REPORT,message="export",metadata={"format":"CSV"});self.assertTrue(result.success);self.assertEqual(self.repo.summary().total,1)
 def test_best_effort_failure(self):
  class Broken:
   def append(self,_record):raise OSError("private detail")
  result=AuditService(Broken()).safe_record(AuditAction.LOGIN_FAILURE,AuditEntityType.SESSION,message="failure");self.assertFalse(result.success)
 def test_disabled_is_noop(self):
  result=AuditService(self.repo,enabled=False).safe_record(AuditAction.LOGIN_SUCCESS,AuditEntityType.SESSION);self.assertFalse(result.success);self.assertEqual(self.repo.summary().total,0)
 def test_message_is_limited_and_flat(self):
  self.service=AuditService(self.repo,message_max_length=5);self.service.record(AuditAction.CONFIG_SAVED,AuditEntityType.CONFIGURATION,message="abcdefgh");self.assertEqual(self.repo.query(AuditQuery())[0].message,"abcde")

