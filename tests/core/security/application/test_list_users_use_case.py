import unittest
from dataclasses import fields

from src.core.security.application import ListUsersUseCase
from src.core.security.domain import UserCreateRequest, UserRole
from tests.core.security.fakes import FakePasswordHasher, InMemoryUserRepository


class ListUsersUseCaseTests(unittest.TestCase):
    def test_returns_safe_user_dtos(self) -> None:
        repository = InMemoryUserRepository()
        repository.create_user(
            UserCreateRequest(
                "11111111-1111-1111-1111-111111111111",
                "viewer",
                "Viewer",
                UserRole.VIEWER,
            ),
            FakePasswordHasher().hash_password("SecurePass1"),
        )

        users = ListUsersUseCase(repository).execute()

        self.assertEqual(users[0].username, "viewer")
        self.assertTrue(
            {"password_hash", "password_salt"}.isdisjoint(
                field.name for field in fields(users[0])
            )
        )


if __name__ == "__main__":
    unittest.main()
