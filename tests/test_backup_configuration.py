import json,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from src.core.backup import BackupSourceCatalog,BackupValidationError
class BackupConfigurationTests(unittest.TestCase):
 def test_project_configuration_limits(self):
  backup=json.loads(Path("config/local_face_validation.dev.json").read_text())["backup"]
  for key in ("maximum_archive_size_bytes","maximum_file_count","operation_history_limit","restore_timeout_seconds","sqlite_snapshot_timeout_seconds"):self.assertGreater(backup[key],0)
  self.assertEqual(backup["directory"],"data/ui_validation/backups")
 def test_symlink_escape_rejected_by_resolver(self):
  with TemporaryDirectory() as d,TemporaryDirectory() as outside:
   root=Path(d);(root/"link").symlink_to(Path(outside),target_is_directory=True)
   with self.assertRaises(BackupValidationError):BackupSourceCatalog(root,{"person_database":{"path":"link/x.db"},"backup":{"include_configuration":False}}).sources()
