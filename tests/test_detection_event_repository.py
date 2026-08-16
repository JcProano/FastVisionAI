import csv
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.core.detection_events import (
    DetectionEventQuery, DetectionEventRecord, DetectionEventRepository,
    DetectionEventRepositoryError, DetectionEventType,
)


def record(event_id="e1", event_type=DetectionEventType.REGISTERED_CANDIDATE,
           person_id="person-1", camera="0", timestamp=None):
    now = timestamp or datetime.now(timezone.utc)
    return DetectionEventRecord(event_id, person_id, event_type, now, camera,
        "Temporary Person", .8, 75.0, "NOT_EVALUATED", "ACTIVE", "session", now)


class DetectionEventRepositoryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name); self.path = self.root / "events.db"
        self.repository = DetectionEventRepository(self.path)
        self.assertEqual(self.repository.initialize(), 1)

    def test_new_database_create_filters_limit_and_schema(self):
        now = datetime.now(timezone.utc)
        self.repository.create(record("a", timestamp=now - timedelta(days=1)))
        self.repository.create(record("b", DetectionEventType.UNREGISTERED, None, timestamp=now))
        self.assertEqual(self.repository.count(), 2)
        self.assertEqual(self.repository.get_by_event_id("a").person_id, "person-1")
        self.assertEqual(len(self.repository.query(DetectionEventQuery(
            date_from=now - timedelta(hours=1), event_type=DetectionEventType.UNREGISTERED,
            limit=1))), 1)
        with sqlite3.connect(self.path) as connection:
            self.assertEqual(connection.execute("SELECT version FROM schema_version").fetchone()[0], 1)
            columns = {row[1] for row in connection.execute("PRAGMA table_info(detection_events)")}
        for forbidden in ("cedula", "address", "phone", "email", "notes", "embedding", "image"):
            self.assertNotIn(forbidden, columns)

    def test_future_schema_is_rejected(self):
        with sqlite3.connect(self.path) as connection:
            connection.execute("UPDATE schema_version SET version=99")
        with self.assertRaises(DetectionEventRepositoryError): self.repository.initialize()

    def test_filters_camera_and_administrative_status(self):
        self.repository.create(record("front", camera="Entrada principal"))
        self.repository.create(record("other", camera="USB Camera"))
        result = self.repository.query(DetectionEventQuery(
            camera_id="Entrada principal", administrative_status="ACTIVE",
        ))
        self.assertEqual(tuple(item.event_id for item in result), ("front",))

    def test_csv_contains_only_allowlisted_columns(self):
        self.repository.create(record())
        destination = self.root / "events.csv"
        self.assertEqual(self.repository.export_csv(destination, DetectionEventQuery()), 1)
        with destination.open() as stream: rows = list(csv.reader(stream))
        self.assertEqual(rows[0], ["timestamp", "event_type", "person_id",
            "display_name_snapshot", "similarity", "quality_score", "recognition_state", "camera_id"])
        content = destination.read_text().casefold()
        for forbidden in ("cedula", "address", "phone", "email", "embedding", "thumbnail"):
            self.assertNotIn(forbidden, content)


if __name__ == "__main__": unittest.main()
