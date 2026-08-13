import dataclasses
import tempfile
import unittest
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from src.core.attendance import AttendancePolicy, AttendanceRepository, AttendanceService
from src.core.person_database import PersonCreateRequest, PersonRepository, PersonStatus
from src.ui.attendance import AttendanceUIController
from src.ui.attendance.tk_window import AttendanceHistoryWindow, _parse_date
from src.ui.person_profile.tk_window import PersonProfileWindow


class AttendanceUITests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.people = PersonRepository(root / "people.db"); self.people.initialize()
        self.person_id = str(uuid.uuid4())
        self.people.create(PersonCreateRequest(
            self.person_id, "1710034065", "Temporary", "Operator",
        ))
        self.people.set_status(self.person_id, PersonStatus.ACTIVE)
        repository = AttendanceRepository(root / "attendance.db"); repository.initialize()
        service = AttendanceService(repository, self.people, AttendancePolicy(
            enabled=True, allow_manual_events=True, policy_name="test", policy_version="1",
        ))
        self.controller = AttendanceUIController(service, repository, self.people)

    def test_dto_resolves_safe_name_and_masked_cedula(self):
        self.controller.manual_check_in(self.person_id)
        dto = self.controller.list().events[0]
        self.assertEqual(dto.display_name, "Temporary Operator")
        self.assertEqual(dto.masked_cedula, "******4065")
        fields = {field.name for field in dataclasses.fields(dto)}
        self.assertFalse(fields & {
            "address", "phone", "email", "embedding", "template", "thumbnail", "image",
        })

    def test_person_summary_does_not_load_unbounded_history(self):
        self.controller.manual_check_in(self.person_id)
        event = self.controller.list().events[0]
        from zoneinfo import ZoneInfo
        local_day = event.timestamp.astimezone(ZoneInfo("America/Guayaquil")).date()
        summary = self.controller.person_summary(self.person_id, local_day)
        self.assertIsNotNone(summary.last_check_in)
        self.assertEqual(summary.events_today, 1)

    def test_date_filters_are_utc_day_boundaries(self):
        start = _parse_date("2026-01-02", end=False)
        end = _parse_date("2026-01-02", end=True)
        self.assertEqual(start, datetime(2026, 1, 2, tzinfo=timezone.utc))
        self.assertEqual(end.date(), start.date())
        self.assertIsNone(_parse_date("", end=False))

    def test_profile_manual_confirmation_cancelled_has_no_write(self):
        window = PersonProfileWindow.__new__(PersonProfileWindow)
        window.person_id = self.person_id
        window._profile = Mock(display_name="Temporary Operator")
        window.controller = Mock()
        window.window = object()
        window.status = Mock()
        with patch("src.ui.person_profile.tk_window.messagebox.askyesno", return_value=False):
            window.manual_attendance(True)
        window.controller.manual_attendance.assert_not_called()

    def test_history_focus_is_singleton_reuse_operation(self):
        window = AttendanceHistoryWindow.__new__(AttendanceHistoryWindow)
        window.window = Mock()
        window.focus()
        window.window.lift.assert_called_once()
        window.window.focus_force.assert_called_once()


if __name__ == "__main__":
    unittest.main()
