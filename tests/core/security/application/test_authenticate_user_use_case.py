import unittest
from datetime import datetime, timezone

from src.core.security.application import AuthenticateUserUseCase
from src.core.security.domain import (
    AuthenticationPolicy,
    AuthenticationRequest,
    UserCreateRequest,
    UserRole,
)
from tests.core.security.fakes import (
    FakePasswordHasher,
    InMemoryUserRepository,
)


class AuthenticateUserUseCaseTests(unittest.TestCase):
    def test_success_and_failure_use_the_same_port_boundary(self) -> None:
        repository = InMemoryUserRepository()
        hasher = FakePasswordHasher()
        repository.create_user(
            UserCreateRequest(
                "11111111-1111-1111-1111-111111111111",
                "admin",
                "Admin",
                UserRole.ADMIN,
            ),
            hasher.hash_password("SecurePass1"),
        )
        use_case = AuthenticateUserUseCase(
            repository,
            hasher,
            AuthenticationPolicy(2, 30),
            now=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

        missing = use_case.execute(AuthenticationRequest("missing", "WrongPass1"))
        success = use_case.execute(AuthenticationRequest("admin", "SecurePass1"))

        self.assertFalse(missing.success)
        self.assertTrue(success.success)
        self.assertEqual(success.user.username, "admin")

    def test_failed_attempts_create_an_explicit_lockout(self) -> None:
        repository = InMemoryUserRepository()
        hasher = FakePasswordHasher()
        user = repository.create_user(
            UserCreateRequest(
                "11111111-1111-1111-1111-111111111111",
                "admin",
                "Admin",
                UserRole.ADMIN,
            ),
            hasher.hash_password("SecurePass1"),
        )
        use_case = AuthenticateUserUseCase(
            repository,
            hasher,
            AuthenticationPolicy(1, 30),
            now=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

        result = use_case.execute(AuthenticationRequest("admin", "WrongPass1"))

        self.assertTrue(result.temporarily_unavailable)
        self.assertIsNotNone(repository.records[user.user_id].locked_until)


if __name__ == "__main__":
    unittest.main()
