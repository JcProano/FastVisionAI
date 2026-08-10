import inspect,unittest
from src.ui.security.login_window import LoginWindow
class LoginWindowTests(unittest.TestCase):
 def test_password_is_masked_and_camera_is_unknown(self):
  source=inspect.getsource(LoginWindow);self.assertIn('show="•"',source);self.assertNotIn("CameraManager",source);self.assertNotIn("password_hash",source)
