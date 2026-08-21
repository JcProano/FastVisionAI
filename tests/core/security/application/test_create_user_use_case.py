import unittest

from src.core.security.application import CreateUserUseCase
from src.core.security.domain import UserRole
from tests.core.security.fakes import FakePasswordHasher, InMemoryUserRepository


class CreateUserUseCaseTests(unittest.TestCase):
    def test_creates_and_audits_one_user(self) -> None:
        repository = InMemoryUserRepository()
        audits = []
        use_case = CreateUserUseCase(
            repository,
            FakePasswordHasher(),
            lambda event, payload: audits.append((event, payload)),
            new_id=lambda: "11111111-1111-1111-1111-111111111111",
        )

        user = use_case.execute(
            "operator", "Operator", "SecurePass1", UserRole.OPERATOR
        )

        self.assertEqual(user.role, UserRole.OPERATOR)
        self.assertEqual(audits, [("USER_CREATED", {"user_id": user.user_id})])


if __name__ == "__main__":
    unittest.main()
