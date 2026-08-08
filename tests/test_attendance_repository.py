import csv
import sqlite3
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from src.core.attendance import (
    AttendanceEventType, AttendanceQuery, AttendanceRecord,
    AttendanceRepository, AttendanceRepositoryError,
)


class AttendanceRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.repository = AttendanceRepository(self.root / "nested" / "attendance.db")
        self.assertEqual(self.repository.initialize(), 1)
        self.now = datetime(2026, 1, 2, 12, tzinfo=timezone.utc)

    def tearDown(self):
        self.temporary.cleanup()

    def record(self, identifier, person, kind, offset=0):
        item = AttendanceRecord(
            identifier, person, kind, self.now + timedelta(seconds=offset),
            f"event-{identifier}", "camera-test", None, self.now, None,
        )
        return self.repository.create(item)

    def test_create_get_list_count_and_query(self):
        item = self.record("a", "person-a", AttendanceEventType.MANUAL_CHECK_IN)
        self.assertEqual(self.repository.get_by_id("a"), item)
        self.assertEqual(self.repository.count(), 1)
        self.assertEqual(self.repository.list(), (item,))
        self.assertEqual(self.repository.query(AttendanceQuery(person_id="person-a")), (item,))

    def test_latest_uses_timestamp_and_deterministic_id_tiebreak(self):
        self.record("a", "person", AttendanceEventType.CHECK_IN)
        later = self.record("b", "person", AttendanceEventType.CHECK_OUT, 2)
        self.assertEqual(self.repository.latest_for_person("person"), later)
        tied = self.record("z", "person", AttendanceEventType.CHECK_IN, 2)
        self.assertEqual(self.repository.latest_for_person("person"), tied)

    def test_daily_summary_combines_manual_and_automatic(self):
        kinds = (
            AttendanceEventType.CHECK_IN, AttendanceEventType.MANUAL_CHECK_IN,
            AttendanceEventType.CHECK_OUT, AttendanceEventType.MANUAL_CHECK_OUT,
        )
        for index, kind in enumerate(kinds):
            self.record(str(index), f"person-{index % 2}", kind, index)
        summary = self.repository.daily_summary(date(2026, 1, 2))
        self.assertEqual((summary.total_check_ins, summary.total_check_outs), (2, 2))
        self.assertEqual(summary.unique_people, 2)

    def test_csv_contains_only_approved_columns(self):
        self.record("a", "person", AttendanceEventType.MANUAL_CHECK_IN)
        destination = self.root / "export.csv"
        self.repository.export_csv(destination, AttendanceQuery())
        with destination.open(newline="", encoding="utf-8") as stream:
            rows = list(csv.reader(stream))
        self.assertEqual(rows[0], [
            "timestamp", "person_id", "event_type", "camera_id", "source_event_id",
        ])
        self.assertNotIn("cedula", destination.read_text(encoding="utf-8").lower())
        with self.assertRaises(AttendanceRepositoryError):
            self.repository.export_csv(destination, AttendanceQuery())

    def test_future_schema_is_rejected(self):
        database = self.root / "future.db"
        connection = sqlite3.connect(database)
        connection.execute("CREATE TABLE schema_version(version INTEGER NOT NULL)")
        connection.execute("INSERT INTO schema_version VALUES (99)")
        connection.commit(); connection.close()
        with self.assertRaises(AttendanceRepositoryError):
            AttendanceRepository(database).initialize()

    def test_timeout_must_be_positive(self):
        with self.assertRaises(ValueError):
            AttendanceRepository(self.root / "bad.db", timeout=0)


if __name__ == "__main__":
    unittest.main()
