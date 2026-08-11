import inspect,unittest
from src.ui.backup.tk_window import BackupWindow
class BackupWindowTests(unittest.TestCase):
 def test_window_is_async_singleton_compatible_and_warns(self):
  source=inspect.getsource(BackupWindow);self.assertIn("threading.Thread",source);self.assertIn("información sensible y no está cifrado",source);self.assertIn("def focus",source)
 def test_no_sensitive_payload_language(self):
  source=inspect.getsource(BackupWindow);self.assertNotIn("embedding",source);self.assertNotIn("password_hash",source)
