import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from src.core.configuration import *
class ValidatorTests(unittest.TestCase):
 def test_unknown_rules_by_profile(self):
  with TemporaryDirectory() as d:
   validator=ConfigurationValidator(Path(d));candidate={"unknown":{},"security":{"mystery":1}}
   self.assertFalse(validator.validate(candidate,ConfigurationProfile.DEVELOPMENT).valid);self.assertFalse(validator.validate(candidate,ConfigurationProfile.TESTING).valid);production=validator.validate(candidate,ConfigurationProfile.PRODUCTION);self.assertTrue(production.valid);self.assertEqual(len(production.warnings),2)
 def test_paths_traversal_absolute_and_symlink_escape(self):
  with TemporaryDirectory() as d,TemporaryDirectory() as outside:
   root=Path(d);validator=ConfigurationValidator(root)
   for value in ("../x","/tmp/x"):self.assertFalse(validator.validate({"security":{"database_path":value}},ConfigurationProfile.DEVELOPMENT).valid)
   (root/"link").symlink_to(outside,target_is_directory=True);self.assertFalse(validator.validate({"security":{"database_path":"link/x.db"}},ConfigurationProfile.DEVELOPMENT).valid)
 def test_current_project_config_valid(self):
  import json
  candidate=json.loads(Path("config/local_face_validation.dev.json").read_text());self.assertTrue(ConfigurationValidator(Path.cwd()).validate(candidate,ConfigurationProfile.DEVELOPMENT).valid)
