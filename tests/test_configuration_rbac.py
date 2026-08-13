import json,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from src.core.configuration import *
from src.core.security import AuthorizationReason,AuthorizationResult
from src.ui.configuration import ConfigurationController
class Auth:
 def __init__(self,allowed):self.allowed=allowed
 def require(self,p):return AuthorizationResult(True,self.allowed,"ADMIN",p.value,AuthorizationReason.AUTHORIZED if self.allowed else AuthorizationReason.PERMISSION_DENIED)
class RBACTests(unittest.TestCase):
 def service(self,root):
  path=root/"x.json";path.write_text('{"config_schema_version":1}');return ConfigurationService(ConfigurationLoader(ConfigurationValidator(root)),path,ConfigurationProfile.DEVELOPMENT)
 def test_view_and_edit_denied(self):
  with TemporaryDirectory() as d:
   controller=ConfigurationController(self.service(Path(d)),Auth(False))
   with self.assertRaises(PermissionError):controller.current()
   with self.assertRaises(PermissionError):controller.save_text('{}')
 def test_view_allowed_and_edit_allowed(self):
  with TemporaryDirectory() as d:
   controller=ConfigurationController(self.service(Path(d)),Auth(True));self.assertIsNotNone(controller.current());self.assertTrue(controller.save_text('{"config_schema_version":1}').success)
 def test_explicit_security_disabled_bypass(self):
  with TemporaryDirectory() as d:self.assertIsNotNone(ConfigurationController(self.service(Path(d)),None,security_disabled=True).current())
