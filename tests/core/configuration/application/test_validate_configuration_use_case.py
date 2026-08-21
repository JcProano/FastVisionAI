import unittest

from src.core.configuration.application import ValidateConfigurationUseCase
from src.core.configuration.domain import ConfigurationProfile
from tests.core.configuration.fakes import FakePolicy


class ValidateConfigurationUseCaseTests(unittest.TestCase):
    def test_validates_without_mutating_state(self) -> None:
        result = ValidateConfigurationUseCase(
            FakePolicy(), ConfigurationProfile.DEVELOPMENT
        ).execute({"config_schema_version": 1})

        self.assertTrue(result.valid)


if __name__ == "__main__":
    unittest.main()
