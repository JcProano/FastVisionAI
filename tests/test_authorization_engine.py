import unittest
from src.core.security import *
class AuthorizationTests(unittest.TestCase):
 def test_role_matrix(self):
  engine=AuthorizationEngine();self.assertTrue(engine.evaluate(UserRole.ADMIN,AuthorizationPermission.MANAGE_USERS).allowed);self.assertTrue(engine.evaluate(UserRole.OPERATOR,AuthorizationPermission.ENROLL_PERSON).allowed);self.assertFalse(engine.evaluate(UserRole.OPERATOR,AuthorizationPermission.MANAGE_USERS).allowed);self.assertTrue(engine.evaluate(UserRole.AUDITOR,AuthorizationPermission.EXPORT_REPORTS).allowed);self.assertFalse(engine.evaluate(UserRole.VIEWER,AuthorizationPermission.EDIT_PERSON).allowed)
 def test_unknown_and_disabled(self):
  self.assertEqual(AuthorizationEngine().evaluate("bad",AuthorizationPermission.VIEW_DASHBOARD).reason,AuthorizationReason.UNKNOWN_ROLE);result=AuthorizationEngine(enabled=False).evaluate(None,"anything");self.assertTrue(result.allowed);self.assertEqual(result.reason,AuthorizationReason.AUTHORIZATION_DISABLED)
