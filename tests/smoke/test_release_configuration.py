from __future__ import annotations
import json,unittest
from pathlib import Path
from src.core.configuration import ConfigurationLoader,ConfigurationProfile,ConfigurationValidator
from src.version import __version__

ROOT=Path(__file__).resolve().parents[2]
class ReleaseConfigurationSmokeTests(unittest.TestCase):
 def test_version(self):self.assertEqual(__version__,"1.0.0-rc1")
 def test_dev_and_prod(self):
  loader=ConfigurationLoader(ConfigurationValidator(ROOT))
  for filename,profile in (("local_face_validation.dev.json",ConfigurationProfile.DEVELOPMENT),("local_face_validation.prod.json",ConfigurationProfile.PRODUCTION)):
   snapshot=loader.load(ROOT/"config"/filename,profile);self.assertEqual(snapshot.schema_version,1)
 def test_production_is_conservative(self):
  value=json.loads((ROOT/"config/local_face_validation.prod.json").read_text())
  self.assertTrue(value["security"]["enabled"] and value["audit"]["enabled"] and value["backup"]["enabled"])
  self.assertFalse(value["recognition"]["automatic_decision_enabled"]);self.assertIsNone(value["recognition"]["match_threshold"]);self.assertFalse(value["attendance"]["automatic_attendance_enabled"]);self.assertFalse(value["action_executor"]["automatic_execution_enabled"])

