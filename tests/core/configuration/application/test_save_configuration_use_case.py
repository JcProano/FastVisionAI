import unittest

from src.core.configuration.application import (
    ConfigurationSession,
    SaveConfigurationUseCase,
)
from src.core.configuration.domain import ConfigurationProfile
from tests.core.configuration.fakes import FakePolicy, FakeStore, snapshot


class SaveConfigurationUseCaseTests(unittest.TestCase):
    def test_invalid_candidate_never_reaches_storage(self) -> None:
        store = FakeStore()
        result = SaveConfigurationUseCase(
            ConfigurationSession(snapshot()),
            FakePolicy(valid=False),
            store,
            ConfigurationProfile.DEVELOPMENT,
        ).execute({"unknown": True})

        self.assertFalse(result.success)
        self.assertEqual(store.save_calls, [])

    def test_success_publishes_only_after_storage(self) -> None:
        stored = snapshot({"camera": {"source": 1}})
        session = ConfigurationSession(snapshot({"camera": {"source": 0}}))
        store = FakeStore(stored)

        result = SaveConfigurationUseCase(
            session,
            FakePolicy(),
            store,
            ConfigurationProfile.DEVELOPMENT,
        ).execute({"camera": {"source": 1}})

        self.assertTrue(result.success)
        self.assertIs(session.current(), stored)


if __name__ == "__main__":
    unittest.main()
