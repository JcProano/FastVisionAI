import unittest
from datetime import datetime, timezone

from src.core.security.application import ChangePasswordUseCase
from tests.core.security.fakes import FakePasswordHasher, InMemoryUserRepository


class ChangePasswordUseCaseTests(unittest.TestCase):
    def test_hashes_before_updating_the_repository(self) -> None:
        repository = InMemoryUserRepository()
        moment = datetime(2026, 1, 1, tzinfo=timezone.utc)

        ChangePasswordUseCase(
            repository, FakePasswordHasher(), now=lambda: moment
        ).execute("user-1", "ChangedPass2")

        user_id, hashed, changed_at = repository.password_changes[0]
        self.assertEqual(user_id, "user-1")
        self.assertEqual(hashed.password_hash, b"ChangedPass2")
        self.assertEqual(changed_at, moment)


if __name__ == "__main__":
    unittest.main()
