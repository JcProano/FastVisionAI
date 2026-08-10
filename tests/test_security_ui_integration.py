import unittest,uuid
from datetime import datetime,timedelta,timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from src.core.security import *
from src.ui.security import AuthorizationController,SecurityController
class SecurityUIIntegrationTests(unittest.TestCase):
 def setUp(self):
  self.temp=TemporaryDirectory();repo=UserRepository(Path(self.temp.name)/"u.db");repo.initialize();now=[datetime(2025,1,1,tzinfo=timezone.utc)];self.now=now;auth=AuthenticationService(repo,PasswordHasher());sessions=AuthenticatedSessionManager(5,now=lambda:now[0]);self.controller=SecurityController(auth,sessions,AuthorizationController(AuthorizationEngine(),sessions))
 def tearDown(self):self.temp.cleanup()
 def test_bootstrap_login_and_timeout_pending(self):
  result=self.controller.bootstrap("admin","Admin","SecurePass1","SecurePass1");self.assertTrue(result.success);self.now[0]+=timedelta(seconds=6);self.assertTrue(self.controller.check_timeout(enrollment_active=True).timeout_pending);self.assertTrue(self.controller.status().authenticated);self.controller.check_timeout(enrollment_active=False);self.assertFalse(self.controller.status().authenticated)
 def test_double_enforcement(self):
  self.controller.bootstrap("admin","Admin","SecurePass1","SecurePass1")
  repository=self.controller.authentication.repository
  viewer=repository.create_user(UserCreateRequest(str(uuid.uuid4()),"viewer","Viewer",UserRole.VIEWER),PasswordHasher().hash_password("SecurePass1"))
  self.controller.sessions.start(viewer)
  self.assertFalse(self.controller.authorization.can(AuthorizationPermission.MANAGE_USERS))
 def test_authenticated_operator_changes_own_password(self):
  self.controller.bootstrap("admin","Admin","SecurePass1","SecurePass1")
  self.assertTrue(self.controller.change_own_password("SecurePass1","ChangedPass2"))
  self.controller.logout()
  self.assertTrue(self.controller.login("admin","ChangedPass2").success)
