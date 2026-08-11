import sqlite3,time,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from src.core.backup import *
class SQLiteSnapshotTests(unittest.TestCase):
 def test_snapshot_schema_and_integrity(self):
  with TemporaryDirectory() as d:
   source=Path(d)/"a.db";target=Path(d)/"b.db"
   with sqlite3.connect(source) as c:c.execute("CREATE TABLE schema_version(version INTEGER)");c.execute("INSERT INTO schema_version VALUES(1)");c.execute("CREATE TABLE values_table(value TEXT)");c.execute("INSERT INTO values_table VALUES('safe')")
   version,created=SQLiteSnapshotProvider().create(source,target);self.assertEqual(version,1);self.assertEqual(SQLiteSnapshotProvider().validate(target,1),1);self.assertTrue(created.tzinfo)
 def test_corrupt_and_future_rejected(self):
  with TemporaryDirectory() as d:
   bad=Path(d)/"bad.db";bad.write_bytes(b"not sqlite")
   with self.assertRaises(BackupIntegrityError):SQLiteSnapshotProvider().validate(bad,1)
   future=Path(d)/"future.db"
   with sqlite3.connect(future) as c:c.execute("CREATE TABLE schema_version(version INTEGER)");c.execute("INSERT INTO schema_version VALUES(2)")
   with self.assertRaises(BackupValidationError):SQLiteSnapshotProvider().validate(future,1)
 def test_timeout_cleans_partial_snapshot(self):
  provider=SQLiteSnapshotProvider(.001)
  with TemporaryDirectory() as d:
   source=Path(d)/"a.db";target=Path(d)/"b.db"
   with sqlite3.connect(source) as c:c.execute("CREATE TABLE schema_version(version INTEGER)");c.execute("INSERT INTO schema_version VALUES(1)")
   with patch("src.core.backup.sqlite_snapshot.time.monotonic",side_effect=[0,1]):
    with self.assertRaises(TimeoutError):provider.create(source,target)
   self.assertFalse(target.exists())
