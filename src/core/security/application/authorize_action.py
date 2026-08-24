"""Evaluate a role and permission through the pure RBAC policy."""

from ..domain.authorization import evaluate_permission
from ..domain.models import AuthorizationResult


class AuthorizeActionUseCase:
    def __init__(self, *, enabled: bool = True) -> None:
        self.enabled = enabled

    def execute(self, role: object, permission: object) -> AuthorizationResult:
        return evaluate_permission(role, permission, enabled=self.enabled)
