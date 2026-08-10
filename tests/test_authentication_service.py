import unittest,uuid
from datetime import datetime,timedelta,timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from src.core.security import *
class AuthenticationTests(unittest.TestCase):
 def setUp(self):
  self.temp=TemporaryDirectory();self.repo=UserRepository(Path(self.temp.name)/"u.db");self.repo.initialize();self.now=datetime(2025,1,1,tzinfo=timezone.utc);self.service=AuthenticationService(self.repo,PasswordHasher(),AuthenticationPolicy(2,30),now=lambda:self.now);self.request=UserCreateRequest(str(uuid.uuid4()),"admin","Admin",UserRole.ADMIN);self.service.bootstrap_admin(self.request,"SecurePass1")
 def tearDown(self):self.temp.cleanup()
 def test_valid_and_indistinguishable_invalid(self):
  missing=self.service.authenticate(AuthenticationRequest("missing","WrongPass1"));wrong=self.service.authenticate(AuthenticationRequest("admin","WrongPass1"));self.assertEqual(missing.message,wrong.message);self.assertTrue(self.service.authenticate(AuthenticationRequest("admin","SecurePass1")).success)
 def test_lockout_expiration_and_reset(self):
  self.service.authenticate(AuthenticationRequest("admin","WrongPass1"));locked=self.service.authenticate(AuthenticationRequest("admin","WrongPass1"));self.assertTrue(locked.temporarily_unavailable);self.assertTrue(self.service.authenticate(AuthenticationRequest("admin","SecurePass1")).temporarily_unavailable);self.now+=timedelta(seconds=31);self.assertTrue(self.service.authenticate(AuthenticationRequest("admin","SecurePass1")).success);self.assertEqual(self.repo.get_by_username("admin").failed_attempts,0)
 def test_disabled(self):
  viewer=self.repo.create_user(UserCreateRequest(str(uuid.uuid4()),"viewer","Viewer",UserRole.VIEWER),PasswordHasher().hash_password("SecurePass1"));self.repo.set_status(viewer.user_id,UserStatus.DISABLED);self.assertFalse(self.service.authenticate(AuthenticationRequest("viewer","SecurePass1")).success)
 def test_second_bootstrap_rejected(self):
  with self.assertRaises(BootstrapError):self.service.bootstrap_admin(UserCreateRequest(str(uuid.uuid4()),"other","Other",UserRole.ADMIN),"SecurePass1")
