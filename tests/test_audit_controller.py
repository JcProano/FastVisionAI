from __future__ import annotations
import tempfile,unittest
from datetime import datetime,timezone
from pathlib import Path
from src.core.audit import *
from src.core.security import AuthorizationEngine,AuthorizationPermission,AuthenticatedSessionManager,UserRole
from src.ui.security.controller import AuthorizationController
from src.ui.audit import AuditController

class Allow:
 def __init__(self,value):self.value=value
 def can(self,_permission):return self.value

class AuditControllerTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.repo=AuditRepository(Path(self.temp.name)/"audit.db");self.repo.initialize();AuditService(self.repo).record(AuditAction.LOGIN_SUCCESS,AuditEntityType.SESSION)
 def tearDown(self):self.temp.cleanup()
 def test_view_and_export_permissions(self):
  controller=AuditController(self.repo,Allow(True));self.assertEqual(controller.query().total,1);self.assertEqual(controller.export_csv(Path(self.temp.name)/"out.csv").count,1)
 def test_denied(self):
  controller=AuditController(self.repo,Allow(False))
  with self.assertRaises(PermissionError):controller.query()
 def test_role_matrix(self):
  engine=AuthorizationEngine()
  for role in (UserRole.ADMIN,UserRole.AUDITOR):self.assertTrue(engine.evaluate(role,AuthorizationPermission.VIEW_AUDIT).allowed);self.assertTrue(engine.evaluate(role,AuthorizationPermission.EXPORT_AUDIT).allowed)
  for role in (UserRole.OPERATOR,UserRole.VIEWER):self.assertFalse(engine.evaluate(role,AuthorizationPermission.VIEW_AUDIT).allowed);self.assertFalse(engine.evaluate(role,AuthorizationPermission.EXPORT_AUDIT).allowed)

