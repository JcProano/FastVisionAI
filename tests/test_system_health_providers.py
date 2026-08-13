import sqlite3,unittest
from datetime import datetime,timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock
from src.core.system_health import *
class ProviderTests(unittest.TestCase):
 def test_camera_states_monotonic(self):
  now=[10.0];args=dict(enabled=lambda:True,worker_alive=lambda:True,camera_state=lambda:"connected",stale_frame_seconds=3,monotonic=lambda:now[0])
  self.assertEqual(CameraHealthProvider(last_frame_monotonic=lambda:None,**args).check().level,HealthLevel.UNKNOWN)
  self.assertEqual(CameraHealthProvider(last_frame_monotonic=lambda:9,**args).check().level,HealthLevel.OK);now[0]=20;self.assertEqual(CameraHealthProvider(last_frame_monotonic=lambda:9,**args).check().level,HealthLevel.WARNING)
  self.assertEqual(CameraHealthProvider(enabled=lambda:True,worker_alive=lambda:False,camera_state=lambda:"disconnected",last_frame_monotonic=lambda:None).check().level,HealthLevel.ERROR)
 def test_database_readonly_missing_disabled_and_no_write(self):
  with TemporaryDirectory() as d:
   path=Path(d)/"db.sqlite";self.assertEqual(SQLiteDatabaseHealthProvider("db",path,enabled=False).check().level,HealthLevel.DISABLED);self.assertFalse(path.exists());self.assertEqual(SQLiteDatabaseHealthProvider("db",path,enabled=True).check().level,HealthLevel.UNKNOWN);self.assertFalse(path.exists())
   with sqlite3.connect(path) as c:c.execute("CREATE TABLE marker(value TEXT)");c.execute("INSERT INTO marker VALUES('same')")
   self.assertEqual(SQLiteDatabaseHealthProvider("db",path).check().level,HealthLevel.OK)
   with sqlite3.connect(path) as c:self.assertEqual(c.execute("SELECT value FROM marker").fetchone()[0],"same")
 def test_worker_qsize_failure_safe(self):
  self.assertEqual(WorkerHealthProvider(lambda:True,queue_depth=lambda:(_ for _ in ()).throw(RuntimeError())).check().level,HealthLevel.ERROR)
 def test_event_bus_disabled(self):
  bus=Mock(enabled=False);self.assertEqual(ApplicationEventBusHealthProvider(bus,None).check().level,HealthLevel.DISABLED);bus.publish.assert_not_called()
 def test_security_unauthenticated(self):
  sessions=Mock();sessions.current.return_value=None;self.assertEqual(SecurityHealthProvider(True,sessions).check().level,HealthLevel.WARNING)
 def test_backup_restoring_and_failed(self):
  maintenance=Mock();maintenance.state.value="RESTORING";self.assertEqual(BackupHealthProvider(True,maintenance).check().level,HealthLevel.WARNING);maintenance.state.value="FAILED";self.assertEqual(BackupHealthProvider(True,maintenance).check().level,HealthLevel.ERROR)
