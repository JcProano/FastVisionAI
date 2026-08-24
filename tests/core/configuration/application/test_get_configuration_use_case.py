import unittest

from src.core.configuration.application import (
    ConfigurationSession,
    GetConfigurationUseCase,
)
from tests.core.configuration.fakes import snapshot


class GetConfigurationUseCaseTests(unittest.TestCase):
    def test_returns_current_immutable_snapshot(self) -> None:
        current = snapshot()
        self.assertIs(
            GetConfigurationUseCase(ConfigurationSession(current)).execute(),
            current,
        )


if __name__ == "__main__":
    unittest.main()
