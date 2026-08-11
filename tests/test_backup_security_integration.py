import unittest
from src.core.backup import *
class MaintenanceTests(unittest.TestCase):
 def test_backup_and_restore_state_machine(self):
  item=ApplicationMaintenanceCoordinator();item.begin_backup();self.assertEqual(item.state,MaintenanceState.BACKUP_IN_PROGRESS);item.end_backup();item.quiesce(cancel_enrollment=lambda:None,close_session=lambda:True,close_windows=lambda:None,cancel_callbacks=lambda:None,timeout_seconds=1);self.assertEqual(item.state,MaintenanceState.QUIESCENT);item.begin_restore();self.assertEqual(item.state,MaintenanceState.RESTORING)
 def test_restore_requires_quiescent_and_worker_failure_is_failed(self):
  item=ApplicationMaintenanceCoordinator()
  with self.assertRaises(RestoreError):item.begin_restore()
  with self.assertRaises(RestoreError):item.quiesce(cancel_enrollment=lambda:None,close_session=lambda:False,close_windows=lambda:None,cancel_callbacks=lambda:None,timeout_seconds=1)
  self.assertEqual(item.state,MaintenanceState.FAILED)
