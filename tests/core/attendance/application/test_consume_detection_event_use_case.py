from __future__ import annotations

import unittest
import uuid
from datetime import datetime, timedelta, timezone

from src.core.attendance.application import ConsumeAttendanceDetectionUseCase
from src.core.attendance.domain.models import AttendanceEventType
from tests.core.attendance.fakes import (
    FakePeopleReader,
    FixedLocalDayClock,
    InMemoryAttendanceRepository,
    attendance_record,
    enabled_policy,
)


class ConsumeAttendanceDetectionUseCaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.person_id = str(uuid.uuid4())
        self.now = datetime(2026, 1, 2, 12, tzinfo=timezone.utc)
        self.day_start = datetime(2026, 1, 2, 5, tzinfo=timezone.utc)
        self.day_end = self.day_start + timedelta(days=1)
        self.people = FakePeopleReader({self.person_id: "ACTIVE"})
        self.repository = InMemoryAttendanceRepository()
        self.clock = FixedLocalDayClock(self.day_start, self.day_end)

    def use_case(self) -> ConsumeAttendanceDetectionUseCase:
        return ConsumeAttendanceDetectionUseCase(
            self.repository,
            self.people,
            enabled_policy(),
            self.clock,
            utcnow=lambda: self.now,
        )

    def test_delegates_the_atomic_toggle_with_explicit_policy_values(self) -> None:
        record = attendance_record(
            self.person_id,
            AttendanceEventType.CHECK_IN,
            self.now,
            source_event_id="detection-1",
        )
        self.repository.toggle_result = ("recorded", record)

        result = self.use_case().execute(
            self.person_id,
            source_event_id="detection-1",
            camera_id="lobby",
            timestamp=self.now,
        )

        self.assertTrue(result.eligible)
        self.assertIs(result.record, record)
        call = self.repository.toggle_calls[0]
        self.assertEqual(call["day_start"], self.day_start)
        self.assertEqual(call["day_end"], self.day_end)
        self.assertEqual(call["duplicate_cooldown_seconds"], 60)
        self.assertEqual(call["minimum_checkout_interval_seconds"], 30)

    def test_invalid_person_id_stops_before_calling_any_adapter(self) -> None:
        result = self.use_case().execute(
            "not-a-uuid", source_event_id="detection-1", timestamp=self.now
        )

        self.assertEqual(result.reason, "invalid_person_id")
        self.assertEqual(self.people.calls, [])
        self.assertEqual(self.repository.toggle_calls, [])
        self.assertEqual(self.clock.calls, [])

    def test_translates_atomic_repository_failure_to_a_safe_result(self) -> None:
        self.repository.fail_on_toggle = True

        result = self.use_case().execute(
            self.person_id, source_event_id="detection-1", timestamp=self.now
        )

        self.assertEqual((result.eligible, result.reason), (False, "persistence_error"))


if __name__ == "__main__":
    unittest.main()
