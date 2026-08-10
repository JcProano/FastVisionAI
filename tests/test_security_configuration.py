import json,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from src.ui.main import build_security
class SecurityConfigurationTests(unittest.TestCase):
 def test_disabled_is_explicit_and_does_not_create_database(self):
  with TemporaryDirectory() as d:
   root=Path(d);controller=build_security({"security":{"enabled":False}},root);self.assertFalse(controller.enabled);self.assertFalse(any(root.iterdir()))
 def test_enabled_failure_is_fail_closed(self):
  with TemporaryDirectory() as d:
   root=Path(d);bad=root/"blocked";bad.write_text("x")
   with self.assertRaises(Exception):build_security({"security":{"enabled":True,"database_path":"blocked/users.db"}},root)
 def test_project_config_has_no_credentials(self):
  config=json.loads(Path("config/local_face_validation.dev.json").read_text());security=config["security"];self.assertNotIn("password",security);self.assertNotIn("username",security)
