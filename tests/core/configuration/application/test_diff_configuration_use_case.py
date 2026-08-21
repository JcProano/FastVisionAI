import unittest

from src.core.configuration.application import (
    ConfigurationSession,
    DiffConfigurationUseCase,
)
from src.core.configuration.domain import ConfigurationImpact
from tests.core.configuration.fakes import FakePolicy, snapshot


class DiffConfigurationUseCaseTests(unittest.TestCase):
    def test_classifies_changes_with_redacted_values(self) -> None:
        session = ConfigurationSession(snapshot({"secret": "old"}))

        result = DiffConfigurationUseCase(session, FakePolicy()).execute(
            {"secret": "new"}
        )

        self.assertEqual(result.changes[0].old_value, "[REDACTED]")
        self.assertIs(
            result.changes[0].impact, ConfigurationImpact.RESTART_REQUIRED
        )


if __name__ == "__main__":
    unittest.main()
