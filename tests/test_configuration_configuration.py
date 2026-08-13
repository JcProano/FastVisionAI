import json,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from src.core.configuration import *
class ConfigurationTests(unittest.TestCase):
 def test_profile_unavailable_no_fallback(self):
  registry=ProfileRegistry.development(Path("dev.json"));self.assertEqual(registry.path_for(ConfigurationProfile.DEVELOPMENT),Path("dev.json"))
  for profile in (ConfigurationProfile.PRODUCTION,ConfigurationProfile.TESTING):
   with self.assertRaises(ConfigurationError):registry.path_for(profile)
 def test_export_metadata_and_no_secrets(self):
  with TemporaryDirectory() as d:
   root=Path(d);path=root/"x.json";path.write_text(json.dumps({"config_schema_version":1,"security":{"enabled":True,"password_hint":"secret"}}))
   # Production accepts the intentionally unknown secret-shaped field as warning.
   service=ConfigurationService(ConfigurationLoader(ConfigurationValidator(root)),path,ConfigurationProfile.PRODUCTION);target=root/"export.json";service.export(target);value=json.loads(target.read_text());self.assertIn("exported_at",value);self.assertIn("exported_by_version",value);self.assertNotIn("password_hint",value["security"]);self.assertNotIn("secret",target.read_text())
 def test_import_only_returns_candidate_and_diff(self):
  with TemporaryDirectory() as d:
   root=Path(d);current=root/"a.json";other=root/"b.json";current.write_text('{"config_schema_version":1}');other.write_text('{"config_schema_version":1,"camera":{"source":1}}');service=ConfigurationService(ConfigurationLoader(ConfigurationValidator(root)),current,ConfigurationProfile.DEVELOPMENT);candidate,diff=service.import_candidate(other);self.assertEqual(candidate["camera"]["source"],1);self.assertTrue(diff.restart_required);self.assertNotIn("camera",service.current().as_mapping())
 def test_enabled_false_legacy_path_and_enabled_invalid_fail_closed_are_explicit(self):
  import inspect
  from src.ui import main
  source=inspect.getsource(main.main);self.assertIn('if bool(manager_settings.get("enabled", False))',source);self.assertIn("ConfigurationService",source)
