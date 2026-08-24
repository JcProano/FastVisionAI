import unittest

from src.core.security.application import AuthorizeActionUseCase
from src.core.security.domain import AuthorizationPermission, UserRole


class AuthorizeActionUseCaseTests(unittest.TestCase):
    def test_applies_the_domain_role_matrix(self) -> None:
        use_case = AuthorizeActionUseCase()

        self.assertTrue(
            use_case.execute(
                UserRole.ADMIN, AuthorizationPermission.MANAGE_USERS
            ).allowed
        )
        self.assertFalse(
            use_case.execute(
                UserRole.VIEWER, AuthorizationPermission.MANAGE_USERS
            ).allowed
        )


if __name__ == "__main__":
    unittest.main()
