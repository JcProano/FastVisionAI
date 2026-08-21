import unittest

from src.core.security.application import BootstrapAdminUseCase
from src.core.security.domain import UserCreateRequest, UserRole
from tests.core.security.fakes import FakePasswordHasher, InMemoryUserRepository


class BootstrapAdminUseCaseTests(unittest.TestCase):
    def test_hashes_and_creates_the_initial_administrator(self) -> None:
        repository = InMemoryUserRepository()
        result = BootstrapAdminUseCase(
            repository, FakePasswordHasher()
        ).execute(
            UserCreateRequest(
                "11111111-1111-1111-1111-111111111111",
                "admin",
                "Admin",
                UserRole.ADMIN,
            ),
            "SecurePass1",
        )

        self.assertTrue(result.success)
        self.assertEqual(repository.count_users(), 1)


if __name__ == "__main__":
    unittest.main()
