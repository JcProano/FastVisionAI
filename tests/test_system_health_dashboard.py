import inspect,unittest
from src.ui.tk_app import LocalFaceTkApp
class DashboardTests(unittest.TestCase):
 def test_observes_only_consumed_visual_and_cancels_callback(self):
  source=inspect.getsource(LocalFaceTkApp);self.assertIn("observe_frame",source);self.assertIn("_system_health_after_id",source);self.assertIn("after_cancel",source);self.assertIn("processing_latency",source)
 def test_disabled_has_no_periodic_work(self):
  source=inspect.getsource(LocalFaceTkApp);self.assertIn("if self._system_health_controller is not None",source)
