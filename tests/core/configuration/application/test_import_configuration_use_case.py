import unittest
from pathlib import Path

from src.core.configuration.application import (
    ConfigurationSession,
    ImportConfigurationUseCase,
)
from src.core.configuration.domain import ConfigurationProfile
from tests.core.configuration.fakes import FakeLoader, FakePolicy, snapshot


class ImportConfigurationUseCaseTests(unittest.TestCase):
    def test_returns_candidate_and_diff_without_applying(self) -> None:
        current = snapshot({"camera": {"source": 0}})
        imported = snapshot({"camera": {"source": 1}})
        session = ConfigurationSession(current)

        candidate, difference = ImportConfigurationUseCase(
            session,
            FakeLoader(imported),
            FakePolicy(),
            ConfigurationProfile.DEVELOPMENT,
        ).execute(Path("import.json"))

        self.assertEqual(candidate["camera"]["source"], 1)
        self.assertEqual(len(difference.changes), 1)
        self.assertIs(session.current(), current)


if __name__ == "__main__":
    unittest.main()
