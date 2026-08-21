from __future__ import annotations

import unittest
import uuid
from datetime import datetime, timezone

from src.core.attendance.application import ManualCheckOutUseCase
from src.core.attendance.domain.models import AttendanceEventType
from tests.core.attendance.fakes import FakePeopleReader, InMemoryAttendanceRepository, enabled_policy


class ManualCheckOutUseCaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.person_id = str(uuid.uuid4())
        self.now = datetime(2026, 1, 2, 12, tzinfo=timezone.utc)
        self.people = FakePeopleReader({self.person_id: "ACTIVE"})
        self.repository = InMemoryAttendanceRepository()

    def test_records_manual_check_out_as_a_distinct_operation(self) -> None:
        use_case = ManualCheckOutUseCase(
            self.repository,
            self.people,
            enabled_policy(),
            utcnow=lambda: self.now,
        )

        result = use_case.execute(self.person_id, timestamp=self.now)

        self.assertTrue(result.recorded)
        self.assertEqual(result.record.event_type, AttendanceEventType.MANUAL_CHECK_OUT)

    def test_translates_repository_failure_to_a_safe_result(self) -> None:
        self.repository.fail_on_create = True
        use_case = ManualCheckOutUseCase(
            self.repository,
            self.people,
            enabled_policy(),
            utcnow=lambda: self.now,
        )

        result = use_case.execute(self.person_id, timestamp=self.now)

        self.assertEqual((result.success, result.reason), (False, "persistence_error"))


if __name__ == "__main__":
    unittest.main()
