import json,unittest
from pathlib import Path
from src.core.security import AuthorizationEngine,AuthorizationPermission,UserRole
class ConfigurationTests(unittest.TestCase):
 def test_configuration_positive(self):
  config=json.loads(Path("config/local_face_validation.dev.json").read_text())["system_health"];self.assertTrue(config["enabled"])
  for key in ("dashboard_refresh_seconds","performance_window_seconds","stale_frame_seconds"):self.assertGreater(config[key],0)
 def test_rbac_allowed_all_roles_and_denied_unknown(self):
  engine=AuthorizationEngine()
  for role in UserRole:self.assertTrue(engine.evaluate(role,AuthorizationPermission.VIEW_SYSTEM_HEALTH).allowed)
  self.assertFalse(engine.evaluate("UNKNOWN",AuthorizationPermission.VIEW_SYSTEM_HEALTH).allowed)
