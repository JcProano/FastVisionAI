import unittest,uuid
from datetime import datetime,timedelta,timezone
from src.core.security import *
class SessionTests(unittest.TestCase):
 def user(self):
  now=datetime.now(timezone.utc);return UserDTO(str(uuid.uuid4()),"admin","Admin",UserRole.ADMIN,UserStatus.ACTIVE,0,None,None,now,now,now)
 def test_start_touch_logout_without_password(self):
  now=[datetime(2025,1,1,tzinfo=timezone.utc)];manager=AuthenticatedSessionManager(10,now=lambda:now[0]);session=manager.start(self.user());self.assertTrue(manager.context().authenticated);now[0]+=timedelta(seconds=5);self.assertEqual(manager.touch().last_activity_at,now[0]);manager.logout();self.assertFalse(manager.context().authenticated);self.assertNotIn("password",repr(session).lower())
 def test_idle_timeout(self):
  now=[datetime(2025,1,1,tzinfo=timezone.utc)];manager=AuthenticatedSessionManager(10,now=lambda:now[0]);manager.start(self.user());now[0]+=timedelta(seconds=10);self.assertTrue(manager.is_idle_expired())
