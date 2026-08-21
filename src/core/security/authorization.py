"""Compatibility facade for the explicit authorization use case."""

from .application import AuthorizeActionUseCase
from .domain.authorization import ROLE_PERMISSIONS
from .domain.models import AuthorizationResult


class AuthorizationEngine(AuthorizeActionUseCase):
    def evaluate(self, role: object, permission: object) -> AuthorizationResult:
        return self.execute(role, permission)


__all__ = ["AuthorizationEngine", "ROLE_PERMISSIONS"]
