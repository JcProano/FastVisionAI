import inspect,unittest
from src.ui.system_health import SystemHealthWindow
class WindowTests(unittest.TestCase):
 def test_singleton_compatible_incremental_window(self):
  source=inspect.getsource(SystemHealthWindow);self.assertIn("def focus",source);self.assertIn("configure",source);self.assertNotIn("embedding",source)
