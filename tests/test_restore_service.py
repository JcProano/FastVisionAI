import os,sqlite3,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from src.core.backup import *
from tests.test_backup_service import settings
class RestoreServiceTests(unittest.TestCase):
 def setup_bundle(self,root):
  db=root/"data/fastvision/people.db";db.parent.mkdir(parents=True)
  with sqlite3.connect(db) as c:c.execute("CREATE TABLE schema_version(version INTEGER)");c.execute("INSERT INTO schema_version VALUES(1)");c.execute("CREATE TABLE marker(value TEXT)");c.execute("INSERT INTO marker VALUES('backup')")
  catalog=BackupSourceCatalog(root,settings());archive=BackupArchive();snap=SQLiteSnapshotProvider();BackupService(catalog,archive,snap).create(BackupRequest(root/"x.fvbackup"));return db,catalog,archive,snap
 def quiescent(self,coordinator):coordinator.quiesce(cancel_enrollment=lambda:None,close_session=lambda:True,close_windows=lambda:None,cancel_callbacks=lambda:None,timeout_seconds=1)
 def test_valid_restore_requires_restart(self):
  with TemporaryDirectory() as d:
   root=Path(d);db,catalog,archive,snap=self.setup_bundle(root)
   with sqlite3.connect(db) as c:c.execute("UPDATE marker SET value='changed'")
   coordinator=ApplicationMaintenanceCoordinator();service=RestoreService(catalog,archive,snap,coordinator);plan=service.prepare(root/"x.fvbackup");self.quiescent(coordinator);result=service.restore(plan,confirmed=True)
   self.assertTrue(result.success);self.assertTrue(result.restart_required)
   with sqlite3.connect(db) as c:self.assertEqual(c.execute("SELECT value FROM marker").fetchone()[0],"backup")
 def test_restore_abort_has_no_effect(self):
  with TemporaryDirectory() as d:
   root=Path(d);db,catalog,archive,snap=self.setup_bundle(root);coordinator=ApplicationMaintenanceCoordinator();service=RestoreService(catalog,archive,snap,coordinator);plan=service.prepare(root/"x.fvbackup");result=service.restore(plan,confirmed=False);self.assertFalse(result.success);self.assertTrue(db.exists())
 def test_restore_space_failure_cleans_staging(self):
  class Usage:free=0
  with TemporaryDirectory() as d:
   root=Path(d);_db,catalog,archive,snap=self.setup_bundle(root);service=RestoreService(catalog,archive,snap,ApplicationMaintenanceCoordinator(),disk_usage=lambda _p:Usage())
   with self.assertRaises(BackupSpaceError):service.prepare(root/"x.fvbackup")
 def test_rollback_success_and_failure(self):
  with TemporaryDirectory() as d:
   root=Path(d);db,catalog,archive,snap=self.setup_bundle(root);coordinator=ApplicationMaintenanceCoordinator();service=RestoreService(catalog,archive,snap,coordinator);plan=service.prepare(root/"x.fvbackup");self.quiescent(coordinator);real=os.replace;calls=[0]
   def fail_install(a,b):
    calls[0]+=1
    if calls[0]==2:raise OSError("controlled")
    return real(a,b)
   with patch("src.core.backup.restore.os.replace",side_effect=fail_install):
    with self.assertRaises(RestoreError):service.restore(plan,confirmed=True)
   self.assertTrue(db.exists())
  with TemporaryDirectory() as d:
   root=Path(d);_db,catalog,archive,snap=self.setup_bundle(root);coordinator=ApplicationMaintenanceCoordinator();service=RestoreService(catalog,archive,snap,coordinator);plan=service.prepare(root/"x.fvbackup");self.quiescent(coordinator);calls=[0]
   def fail_after_move(a,b):
    calls[0]+=1
    if calls[0]>=2:raise OSError("controlled")
    return real(a,b)
   with patch("src.core.backup.restore.os.replace",side_effect=fail_after_move):
    with self.assertRaises(RestoreRollbackError):service.restore(plan,confirmed=True)
   self.assertEqual(coordinator.state,MaintenanceState.FAILED)
