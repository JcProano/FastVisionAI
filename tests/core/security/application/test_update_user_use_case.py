import unittest

from src.core.security.application import UpdateUserUseCase
from src.core.security.domain import UserCreateRequest, UserRole
from tests.core.security.fakes import FakePasswordHasher, InMemoryUserRepository


class UpdateUserUseCaseTests(unittest.TestCase):
    def test_role_change_has_a_distinct_audit_event(self) -> None:
        repository = InMemoryUserRepository()
        user = repository.create_user(
            UserCreateRequest(
                "11111111-1111-1111-1111-111111111111",
                "operator",
                "Operator",
                UserRole.OPERATOR,
            ),
            FakePasswordHasher().hash_password("SecurePass1"),
        )
        audits = []

        result = UpdateUserUseCase(
            repository,
            lambda event, payload: audits.append((event, payload)),
        ).execute(user.user_id, role=UserRole.VIEWER)

        self.assertIs(result.role, UserRole.VIEWER)
        self.assertEqual(audits[0][0], "USER_ROLE_CHANGED")


if __name__ == "__main__":
    unittest.main()
