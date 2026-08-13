from __future__ import annotations
import tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from src.core.audit import *

class AuditIntegrationTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.repo=AuditRepository(Path(self.temp.name)/"audit.db");self.repo.initialize();self.service=AuditService(self.repo)
 def tearDown(self):self.temp.cleanup()
 def test_logout_uses_context_captured_before_invalidation(self):
  callback=AuditCallbackAdapter(self.service,lambda:SimpleNamespace(user_id=None,role=None,session_id=None),"security")
  callback("LOGOUT",{"user_id":"actor-id","actor_role":"ADMIN","session_id":"session-id"})
  item=self.repo.query(AuditQuery())[0];self.assertEqual((item.actor_user_id,item.actor_role,item.session_id),("actor-id","ADMIN","session-id"))
 def test_login_failure_is_anonymous_and_has_no_username(self):
  callback=AuditCallbackAdapter(self.service,lambda:SimpleNamespace(user_id=None,role=None,session_id=None),"security")
  callback("LOGIN_FAILURE",{})
  item=self.repo.query(AuditQuery())[0];self.assertIsNone(item.actor_user_id);self.assertEqual(dict(item.metadata),{});self.assertFalse(item.success)
 def test_single_callback_creates_single_record(self):
  callback=AuditCallbackAdapter(self.service,lambda:SimpleNamespace(user_id="admin",role="ADMIN",session_id="s"),"reports")
  callback("REPORT_EXPORTED",{"report_type":"daily","format":"CSV"})
  self.assertEqual(self.repo.summary().total,1)
 def test_person_update_metadata_excludes_civil_pii(self):
  callback=AuditCallbackAdapter(self.service,lambda:SimpleNamespace(user_id="admin",role="ADMIN",session_id="s"),"people")
  callback("PERSON_UPDATED",{"person_id":"person-id"})
  item=self.repo.query(AuditQuery())[0];self.assertEqual(item.entity_id,"person-id");self.assertEqual(dict(item.metadata),{})

