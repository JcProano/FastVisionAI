from __future__ import annotations

import unittest
import uuid
from datetime import datetime, timedelta, timezone
from itertools import count

from src.core.attendance.application import EvaluateAttendanceObservationUseCase
from src.core.attendance.domain.models import AttendanceEventType
from tests.core.attendance.fakes import FakePeopleReader, InMemoryAttendanceRepository, enabled_policy


class EvaluateAttendanceObservationUseCaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.person_id = str(uuid.uuid4())
        self.now = datetime(2026, 1, 2, 12, tzinfo=timezone.utc)
        self.people = FakePeopleReader({self.person_id: "ACTIVE"})
        self.repository = InMemoryAttendanceRepository()

    def test_records_only_after_the_observation_is_stable(self) -> None:
        ticks = count(0.0, 2.0)
        use_case = EvaluateAttendanceObservationUseCase(
            self.repository,
            self.people,
            enabled_policy(),
            monotonic=lambda: next(ticks),
            utcnow=lambda: self.now,
        )

        first = use_case.execute(self.person_id, timestamp=self.now)
        stable = use_case.execute(self.person_id, timestamp=self.now)

        self.assertEqual(first.reason, "observation_not_stable")
        self.assertTrue(stable.eligible)
        self.assertEqual(stable.record.event_type, AttendanceEventType.CHECK_IN)
        self.assertEqual(len(self.repository.records), 1)

    def test_keeps_the_observation_for_retry_after_minimum_interval(self) -> None:
        ticks = count(0.0, 2.0)
        use_case = EvaluateAttendanceObservationUseCase(
            self.repository,
            self.people,
            enabled_policy(),
            monotonic=lambda: next(ticks),
            utcnow=lambda: self.now,
        )
        use_case.execute(self.person_id, timestamp=self.now)
        use_case.execute(self.person_id, timestamp=self.now)

        use_case.execute(
            self.person_id, timestamp=self.now + timedelta(seconds=5)
        )
        blocked = use_case.execute(
            self.person_id, timestamp=self.now + timedelta(seconds=5)
        )
        retried = use_case.execute(
            self.person_id, timestamp=self.now + timedelta(seconds=31)
        )

        self.assertEqual(blocked.reason, "minimum_interval")
        self.assertEqual(retried.record.event_type, AttendanceEventType.CHECK_OUT)

    def test_disabled_automatic_attendance_does_not_touch_ports(self) -> None:
        use_case = EvaluateAttendanceObservationUseCase(
            self.repository,
            self.people,
            enabled_policy(automatic_attendance_enabled=False),
        )

        result = use_case.execute(self.person_id)

        self.assertEqual(result.reason, "automatic_attendance_disabled")
        self.assertEqual(self.people.calls, [])
        self.assertEqual(self.repository.records, [])


if __name__ == "__main__":
    unittest.main()
