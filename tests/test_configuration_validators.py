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
 def test_production_automatic_attendance_requires_explicit_valid_schedule(self):
  with TemporaryDirectory() as d:
   validator=ConfigurationValidator(Path(d));base={"attendance":{"automatic_attendance_enabled":True}}
   self.assertFalse(validator.validate(base,ConfigurationProfile.PRODUCTION).valid)
   base["attendance"]["work_schedule"]={"timezone":"America/Guayaquil","workday_start":"08:00","workday_end":"17:00","late_after":"08:10","overtime_after":"17:00"}
   self.assertTrue(validator.validate(base,ConfigurationProfile.PRODUCTION).valid)
   base["attendance"]["work_schedule"]["late_after"]="8am"
   self.assertFalse(validator.validate(base,ConfigurationProfile.PRODUCTION).valid)
