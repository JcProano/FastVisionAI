import tempfile
import unittest
import uuid
from itertools import count
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.core.attendance import AttendanceEventType, AttendancePolicy, AttendanceRepository, AttendanceService
from src.core.person_database import PersonCreateRequest, PersonRepository, PersonStatus


class AttendanceServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.people = PersonRepository(root / "people.db"); self.people.initialize()
        self.repository = AttendanceRepository(root / "attendance.db"); self.repository.initialize()
        self.person_id = str(uuid.uuid4())
        self.people.create(PersonCreateRequest(
            self.person_id, "1710034065", "Temporary", "Active",
        ))
        self.people.set_status(self.person_id, PersonStatus.ACTIVE)
        self.now = datetime(2026, 1, 2, 12, tzinfo=timezone.utc)

    def service(self, **changes):
        values = dict(
            enabled=True, automatic_attendance_enabled=False,
            minimum_stable_observations=2, minimum_observation_seconds=1,
            duplicate_event_cooldown_seconds=60,
            minimum_time_between_check_in_out_seconds=30,
            allow_manual_events=True, policy_name="test", policy_version="1",
        )
        values.update(changes)
        clock = count(0.0, 2.0)
        return AttendanceService(
            self.repository, self.people, AttendancePolicy(**values),
            monotonic=lambda: next(clock), utcnow=lambda: self.now,
        )

    def test_manual_in_out_remain_distinct(self):
        service = self.service(duplicate_event_cooldown_seconds=0)
        self.assertTrue(service.manual_check_in(self.person_id, timestamp=self.now).success)
        self.assertTrue(service.manual_check_out(
            self.person_id, timestamp=self.now + timedelta(seconds=1),
        ).success)
        self.assertEqual(
            {item.event_type for item in self.repository.list()},
            {AttendanceEventType.MANUAL_CHECK_IN, AttendanceEventType.MANUAL_CHECK_OUT},
        )

    def test_manual_requires_active_existing_person(self):
        pending = str(uuid.uuid4())
        self.people.create(PersonCreateRequest(pending, "0926687856", "Pending", "Person"))
        disabled = str(uuid.uuid4())
        self.people.create(PersonCreateRequest(disabled, "0100000009", "Disabled", "Person"))
        self.people.set_status(disabled, PersonStatus.DISABLED)
        for person_id in (pending, disabled, str(uuid.uuid4())):
            result = self.service().manual_check_in(person_id)
            self.assertFalse(result.success)
            self.assertEqual(result.reason, "person_not_active")
        self.assertEqual(self.repository.count(), 0)

    def test_manual_policy_and_duplicate_cooldown(self):
        service = self.service()
        self.assertTrue(service.manual_check_in(self.person_id, timestamp=self.now).success)
        duplicate = service.manual_check_in(
            self.person_id, timestamp=self.now + timedelta(seconds=10),
        )
        self.assertEqual(duplicate.reason, "duplicate_cooldown")
        self.assertEqual(self.repository.count(), 1)
        self.assertEqual(self.service(enabled=False).manual_check_out(self.person_id).reason,
                         "attendance_disabled")
        self.assertEqual(self.service(allow_manual_events=False).manual_check_out(self.person_id).reason,
                         "manual_events_disabled")

    def test_detection_observation_disabled_is_side_effect_free(self):
        detection_event = object()  # Explicitly represents an upstream DetectionEvent.
        self.assertIsNotNone(detection_event)
        result = self.service().evaluate_observation(self.person_id, source_event_id="event-1")
        self.assertFalse(result.evaluated)
        self.assertEqual(result.reason, "automatic_attendance_disabled")
        self.assertEqual(self.repository.count(), 0)

    def test_explicit_automatic_alternation_and_minimum_interval(self):
        service = self.service(automatic_attendance_enabled=True)
        first = service.evaluate_observation(self.person_id, timestamp=self.now)
        self.assertFalse(first.eligible)
        entered = service.evaluate_observation(self.person_id, timestamp=self.now)
        self.assertTrue(entered.eligible)
        self.assertEqual(entered.record.event_type, AttendanceEventType.CHECK_IN)
        service.evaluate_observation(self.person_id, timestamp=self.now + timedelta(seconds=5))
        blocked = service.evaluate_observation(
            self.person_id, timestamp=self.now + timedelta(seconds=5),
        )
        self.assertEqual(blocked.reason, "minimum_interval")
        exited = service.evaluate_observation(
            self.person_id, timestamp=self.now + timedelta(seconds=31),
        )
        self.assertEqual(exited.record.event_type, AttendanceEventType.CHECK_OUT)

    def test_repository_failure_is_safe(self):
        service = self.service()
        self.repository.create = lambda _item: (_ for _ in ()).throw(RuntimeError("private"))
        result = service.manual_check_in(self.person_id)
        self.assertEqual((result.success, result.reason), (False, "persistence_error"))


if __name__ == "__main__":
    unittest.main()
