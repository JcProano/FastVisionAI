import sqlite3,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from src.core.backup import *
def settings():return {"backup":{"include_configuration":False},"thumbnails":{"directory":"thumbs"}}
class BackupServiceTests(unittest.TestCase):
 def test_empty_and_complete_backup(self):
  with TemporaryDirectory() as d:
   root=Path(d);service=BackupService(BackupSourceCatalog(root,settings()),BackupArchive(),SQLiteSnapshotProvider())
   empty=service.create(BackupRequest(root/"empty.fvbackup"));self.assertEqual(empty.files_count,0);self.assertIn("PEOPLE_DATABASE",empty.missing_components)
   db=root/"data/fastvision/people.db";db.parent.mkdir(parents=True)
   with sqlite3.connect(db) as c:c.execute("CREATE TABLE schema_version(version INTEGER)");c.execute("INSERT INTO schema_version VALUES(1)")
   full=service.create(BackupRequest(root/"full.fvbackup"));self.assertEqual(full.files_count,1);manifest,_=BackupArchive().verify(root/"full.fvbackup");self.assertEqual(manifest.files[0].schema_version,1)
 def test_incomplete_gallery_aborts_without_final(self):
  with TemporaryDirectory() as d:
   root=Path(d);gallery=root/"data/ui_validation/gallery.json";gallery.parent.mkdir(parents=True);gallery.write_text("{}")
   target=root/"bad.fvbackup"
   with self.assertRaises(BackupValidationError):BackupService(BackupSourceCatalog(root,settings()),BackupArchive(),SQLiteSnapshotProvider()).create(BackupRequest(target))
   self.assertFalse(target.exists())
 def test_invalid_thumbnail_filename_aborts(self):
  with TemporaryDirectory() as d:
   root=Path(d);directory=root/"thumbs";directory.mkdir();(directory/"unsafe name.jpg").write_bytes(b"not-an-image");target=root/"bad.fvbackup"
   with self.assertRaises(BackupValidationError):BackupService(BackupSourceCatalog(root,settings()),BackupArchive(),SQLiteSnapshotProvider()).create(BackupRequest(target))
   self.assertFalse(target.exists())
