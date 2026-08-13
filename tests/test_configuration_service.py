import json,threading,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from src.core.configuration import *
class ServiceTests(unittest.TestCase):
 def make(self,root,value=None,backup_count=2):
  path=root/"config"/"active.json";path.parent.mkdir();path.write_text(json.dumps(value or {"config_schema_version":1,"dashboard":{"metrics_refresh_ms":10}}));loader=ConfigurationLoader(ConfigurationValidator(root));return path,ConfigurationService(loader,path,ConfigurationProfile.DEVELOPMENT,backup_count=backup_count)
 def test_current_no_io_and_reload_reports_no_restart_for_hot(self):
  with TemporaryDirectory() as d:
   path,service=self.make(Path(d));path.write_text(json.dumps({"config_schema_version":1,"dashboard":{"metrics_refresh_ms":20}}))
   with patch.object(service.loader,"load",wraps=service.loader.load) as load:self.assertIsNotNone(service.current());load.assert_not_called()
   result=service.reload();self.assertEqual(len(result.diff.hot_reloadable),1);self.assertFalse(service.restart_required_pending)
 def test_reload_restart_required_without_runtime_actions(self):
  with TemporaryDirectory() as d:
   path,service=self.make(Path(d));path.write_text(json.dumps({"config_schema_version":1,"camera":{"source":1}}));result=service.reload();self.assertTrue(service.restart_required_pending);self.assertIn("no fueron reconstruidos",result.message)
 def test_atomic_save_invalid_replace_failure_and_backup(self):
  with TemporaryDirectory() as d:
   root=Path(d);path,service=self.make(root);original=path.read_text();self.assertFalse(service.save({"unknown":1}).success);self.assertEqual(path.read_text(),original)
   with patch("src.core.configuration.service.os.replace",side_effect=OSError("controlled")):self.assertFalse(service.save({"config_schema_version":1,"dashboard":{"metrics_refresh_ms":20}}).success)
   self.assertEqual(path.read_text(),original);result=service.save({"config_schema_version":1,"dashboard":{"metrics_refresh_ms":20}});self.assertTrue(result.success);self.assertTrue(tuple((path.parent/"backups").glob("*.json")))
 def test_rotation_failure_is_success_warning(self):
  with TemporaryDirectory() as d:
   _path,service=self.make(Path(d))
   with patch.object(service,"_rotate",side_effect=OSError("controlled")):result=service.save({"config_schema_version":1})
   self.assertTrue(result.success);self.assertIsNotNone(result.warning)
 def test_temp_validation_failure_preserves_original(self):
  with TemporaryDirectory() as d:
   path,service=self.make(Path(d));original=path.read_text();real=service.loader.load
   def fail_temporary(candidate,profile):
    if candidate.suffix==".tmp":raise ConfigurationError("controlled")
    return real(candidate,profile)
   with patch.object(service.loader,"load",side_effect=fail_temporary):result=service.save({"config_schema_version":1})
   self.assertFalse(result.success);self.assertEqual(path.read_text(),original)
 def test_backup_rotation_limit(self):
  with TemporaryDirectory() as d:
   path,service=self.make(Path(d),backup_count=2)
   for value in range(4):self.assertTrue(service.save({"config_schema_version":1,"camera":{"source":value}}).success)
   self.assertLessEqual(len(tuple((path.parent/"backups").glob("*.json"))),2)
 def test_concurrent_current_reload(self):
  with TemporaryDirectory() as d:
   _path,service=self.make(Path(d));errors=[]
   threads=[threading.Thread(target=lambda:[service.current() for _ in range(100)]),threading.Thread(target=lambda:[service.reload() for _ in range(20)])]
   for t in threads:t.start()
   for t in threads:t.join()
   self.assertFalse(errors)
