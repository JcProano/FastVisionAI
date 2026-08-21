import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.core.configuration.application import (
    ConfigurationSession,
    ExportConfigurationUseCase,
)
from tests.core.configuration.fakes import FakePolicy, FakeStore, snapshot


class ExportConfigurationUseCaseTests(unittest.TestCase):
    def test_exports_a_redacted_copy_with_provenance(self) -> None:
        store = FakeStore()

        ExportConfigurationUseCase(
            ConfigurationSession(snapshot({"secret": "value"})),
            FakePolicy(),
            store,
            application_version="test",
            now=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
        ).execute(Path("export.json"))

        value, destination, overwrite = store.export_calls[0]
        self.assertEqual(value["secret"], "[REDACTED]")
        self.assertEqual(value["exported_by_version"], "test")
        self.assertEqual((destination, overwrite), (Path("export.json"), False))


if __name__ == "__main__":
    unittest.main()
