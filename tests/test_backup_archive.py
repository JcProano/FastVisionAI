import hashlib,json,unittest,zipfile
from datetime import datetime,timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from src.core.backup import *
class BackupArchiveTests(unittest.TestCase):
 def make(self,root):
  payload=root/"x";payload.write_bytes(b"abc");entry=BackupFileEntry("x","components/x",BackupComponentType.CONFIGURATION,3,hashlib.sha256(b"abc").hexdigest());manifest=BackupManifest(1,datetime.now(timezone.utc),"FastVisionAI","test","id","NONE",(entry,),());path=root/"x.fvbackup";BackupArchive().create(path,manifest,{entry.archive_path:payload});return path
 def test_atomic_archive_and_verify(self):
  with TemporaryDirectory() as d:
   path=self.make(Path(d));manifest,_=BackupArchive().verify(path);self.assertEqual(manifest.backup_id,"id");self.assertFalse(any(p.suffix==".tmp" for p in Path(d).iterdir()))
 def test_duplicate_zip_entry_and_traversal(self):
  with TemporaryDirectory() as d:
   for name in ("same","../escape"):
    path=Path(d)/(name.replace('/','_')+".zip")
    with zipfile.ZipFile(path,"w") as z:z.writestr("manifest.json",b"{}");z.writestr(name,b"a");z.writestr(name,b"b")
    with self.assertRaises(BackupValidationError):BackupArchive().verify(path)
 def test_checksum_size_and_unsupported_version(self):
  with TemporaryDirectory() as d:
   path=self.make(Path(d))
   with zipfile.ZipFile(path,"a") as z:z.writestr("unexpected",b"x")
   with self.assertRaises(BackupValidationError):BackupArchive().verify(path)
   with self.assertRaises(BackupValidationError):parse_manifest(json.dumps({"format_version":99}).encode())
 def test_archive_bomb_limit_and_space(self):
  with TemporaryDirectory() as d:
   root=Path(d);path=self.make(root)
   with self.assertRaises(BackupValidationError):BackupArchive(maximum_archive_size_bytes=1).verify(path)
   class Usage:free=0
   payload=root/"p";payload.write_bytes(b"x");entry=BackupFileEntry("p","p",BackupComponentType.CONFIGURATION,1,hashlib.sha256(b"x").hexdigest());manifest=BackupManifest(1,datetime.now(timezone.utc),"F","1","x","NONE",(entry,),())
   with self.assertRaises(BackupSpaceError):BackupArchive(disk_usage=lambda _p:Usage()).create(root/"no.fvbackup",manifest,{"p":payload})
