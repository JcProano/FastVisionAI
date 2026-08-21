import unittest

from src.core.security.application import ResetUserPasswordUseCase
from tests.core.security.fakes import FakePasswordHasher, InMemoryUserRepository


class ResetUserPasswordUseCaseTests(unittest.TestCase):
    def test_resets_and_audits_without_exposing_password(self) -> None:
        repository = InMemoryUserRepository()
        audits = []

        ResetUserPasswordUseCase(
            repository,
            FakePasswordHasher(),
            lambda event, payload: audits.append((event, payload)),
        ).execute("user-1", "ChangedPass2")

        self.assertEqual(repository.password_changes[0][0], "user-1")
        self.assertEqual(audits, [("PASSWORD_RESET", {"user_id": "user-1"})])


if __name__ == "__main__":
    unittest.main()
