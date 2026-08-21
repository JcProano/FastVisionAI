from __future__ import annotations

import unittest
import uuid
from datetime import datetime, timedelta, timezone

from src.core.attendance.application import ManualCheckInUseCase
from src.core.attendance.domain.models import AttendanceEventType
from tests.core.attendance.fakes import (
    FakePeopleReader,
    InMemoryAttendanceRepository,
    attendance_record,
    enabled_policy,
)


class ManualCheckInUseCaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.person_id = str(uuid.uuid4())
        self.now = datetime(2026, 1, 2, 12, tzinfo=timezone.utc)
        self.people = FakePeopleReader({self.person_id: "ACTIVE"})
        self.repository = InMemoryAttendanceRepository()

    def use_case(self) -> ManualCheckInUseCase:
        return ManualCheckInUseCase(
            self.repository,
            self.people,
            enabled_policy(),
            utcnow=lambda: self.now,
        )

    def test_records_manual_check_in_with_its_input_metadata(self) -> None:
        result = self.use_case().execute(
            self.person_id,
            timestamp=self.now,
            camera_id="front-door",
            notes="  authorized by supervisor  ",
        )

        self.assertTrue(result.success)
        self.assertEqual(result.record.event_type, AttendanceEventType.MANUAL_CHECK_IN)
        self.assertEqual(result.record.camera_id, "front-door")
        self.assertEqual(result.record.notes, "authorized by supervisor")
        self.assertEqual(self.repository.records, [result.record])

    def test_rejects_duplicate_check_in_without_writing(self) -> None:
        existing = attendance_record(
            self.person_id, AttendanceEventType.MANUAL_CHECK_IN, self.now
        )
        self.repository.records.append(existing)

        result = self.use_case().execute(
            self.person_id, timestamp=self.now + timedelta(seconds=10)
        )

        self.assertEqual(result.reason, "duplicate_cooldown")
        self.assertEqual(self.repository.records, [existing])

    def test_rejects_a_person_that_is_not_active(self) -> None:
        result = self.use_case().execute(str(uuid.uuid4()), timestamp=self.now)

        self.assertEqual(result.reason, "person_not_active")
        self.assertEqual(self.repository.records, [])


if __name__ == "__main__":
    unittest.main()
