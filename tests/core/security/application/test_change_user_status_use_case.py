import unittest

from src.core.security.application import ChangeUserStatusUseCase
from src.core.security.domain import UserCreateRequest, UserRole, UserStatus
from tests.core.security.fakes import FakePasswordHasher, InMemoryUserRepository


class ChangeUserStatusUseCaseTests(unittest.TestCase):
    def test_authenticated_user_cannot_disable_itself(self) -> None:
        repository = InMemoryUserRepository()
        user = repository.create_user(
            UserCreateRequest(
                "11111111-1111-1111-1111-111111111111",
                "admin",
                "Admin",
                UserRole.ADMIN,
            ),
            FakePasswordHasher().hash_password("SecurePass1"),
        )

        with self.assertRaises(PermissionError):
            ChangeUserStatusUseCase(repository).execute(
                user.user_id,
                UserStatus.DISABLED,
                actor_user_id=user.user_id,
            )

        self.assertIs(repository.records[user.user_id].status, UserStatus.ACTIVE)


if __name__ == "__main__":
    unittest.main()
