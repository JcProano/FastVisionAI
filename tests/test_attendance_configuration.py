import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.ui.main import build_attendance


class AttendanceConfigurationTests(unittest.TestCase):
    def test_disabled_does_not_resolve_path_or_create_repository(self):
        with patch("src.ui.main.AttendanceRepository") as repository:
            self.assertIsNone(build_attendance({"attendance": {"enabled": False}}, None))
        repository.assert_not_called()

    def test_enabled_uses_project_relative_path_and_safe_defaults(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            people = object()
            with patch("src.ui.main.AttendanceRepository") as repository_type:
                repository = repository_type.return_value
                controller = build_attendance({"attendance": {
                    "enabled": True, "database_path": "state/attendance.db",
                }}, people, root)
            repository_type.assert_called_once_with(
                root / "state" / "attendance.db", timeout=5.0,
            )
            repository.initialize.assert_called_once()
            self.assertFalse(controller.service.policy.automatic_attendance_enabled)
            self.assertTrue(controller.service.policy.allow_manual_events)

    def test_escaping_or_absolute_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for path in ("../attendance.db", "/tmp/attendance.db"):
                with self.assertRaises(ValueError):
                    build_attendance({"attendance": {
                        "enabled": True, "database_path": path,
                    }}, object(), root)

    def test_initialization_failure_disables_attendance(self):
        with tempfile.TemporaryDirectory() as temporary, patch(
            "src.ui.main.AttendanceRepository.initialize", side_effect=RuntimeError("private"),
        ):
            result = build_attendance({"attendance": {
                "enabled": True, "database_path": "attendance.db",
            }}, object(), Path(temporary))
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
