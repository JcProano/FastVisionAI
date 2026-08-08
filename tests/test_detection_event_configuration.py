import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from src.ui.main import build_detection_event_service


class DetectionEventConfigurationTests(unittest.TestCase):
    def test_disabled_does_not_resolve_or_create_database(self):
        settings = {"event_history": {"enabled": False, "database_path": "/unsafe/ignored.db"}}
        self.assertIsNone(build_detection_event_service(settings, Path("/does/not/matter")))

    def test_relative_path_and_traversal_validation(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = {"event_history": {"enabled": True, "database_path": "state/events.db"}}
            service = build_detection_event_service(settings, root)
            self.assertTrue((root / "state/events.db").is_file())
            self.assertIsNotNone(service)
            with self.assertRaises(ValueError):
                build_detection_event_service(
                    {"event_history": {"enabled": True, "database_path": "../events.db"}}, root
                )
            with self.assertRaises(ValueError):
                build_detection_event_service(
                    {"event_history": {"enabled": True, "database_path": "/tmp/events.db"}}, root
                )

    def test_initialization_failure_disables_history_without_stopping_application(self):
        with tempfile.TemporaryDirectory() as temporary, patch(
            "src.ui.main.DetectionEventRepository.initialize", side_effect=OSError("controlled")
        ):
            service = build_detection_event_service(
                {"event_history": {"enabled": True, "database_path": "events.db"}},
                Path(temporary),
            )
            self.assertIsNone(service)


if __name__ == "__main__": unittest.main()
