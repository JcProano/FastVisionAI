import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from src.core.backup import *
from tests.test_backup_service import settings
class BackupVerifierTests(unittest.TestCase):
 def test_verify_and_audit_failure_isolated(self):
  with TemporaryDirectory() as d:
   root=Path(d);events=[];service=BackupService(BackupSourceCatalog(root,settings()),BackupArchive(),SQLiteSnapshotProvider(),audit_callback=lambda event,_data:(_ for _ in ()).throw(RuntimeError()))
   service.create(BackupRequest(root/"x.fvbackup"));self.assertTrue(service.verify(root/"x.fvbackup").valid)
