import unittest
from pathlib import Path

from src.core.configuration.application import (
    ConfigurationSession,
    ReloadConfigurationUseCase,
)
from src.core.configuration.domain import ConfigurationProfile
from tests.core.configuration.fakes import FakeLoader, FakePolicy, snapshot


class ReloadConfigurationUseCaseTests(unittest.TestCase):
    def test_replaces_snapshot_and_marks_restart_changes(self) -> None:
        session = ConfigurationSession(snapshot({"camera": {"source": 0}}))
        loaded = snapshot({"camera": {"source": 1}})

        result = ReloadConfigurationUseCase(
            session,
            FakeLoader(loaded),
            FakePolicy(),
            Path("config.json"),
            ConfigurationProfile.DEVELOPMENT,
        ).execute()

        self.assertTrue(result.success)
        self.assertTrue(session.restart_required_pending)
        self.assertIs(session.current(), loaded)


if __name__ == "__main__":
    unittest.main()
