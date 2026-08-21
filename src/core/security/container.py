"""Composition container for operator-security application dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .authentication import AuthenticationService
from .authorization import AuthorizationEngine
from .domain.models import AuthenticationPolicy, PasswordPolicy
from .infrastructure import (
    InMemoryAuthenticatedSessionManager,
    SQLiteUserRepository,
    ScryptPasswordHasher,
)


@dataclass(frozen=True, slots=True)
class SecurityComponents:
    enabled: bool
    bootstrap_enabled: bool
    appliance_mode: bool
    repository: object
    hasher: object
    authentication: AuthenticationService
    sessions: object
    authorization: AuthorizationEngine


class SecurityContainer:
    @staticmethod
    def build(
        settings: dict[str, object],
        project_root: Path,
        *,
        repository_type=SQLiteUserRepository,
        hasher_type=ScryptPasswordHasher,
        session_type=InMemoryAuthenticatedSessionManager,
        authentication_type=AuthenticationService,
        authorization_type=AuthorizationEngine,
    ) -> SecurityComponents:
        configuration = settings.get("security", {})
        if not isinstance(configuration, dict):
            raise ValueError("security configuration must be an object")
        enabled = bool(configuration.get("enabled", True))
        sessions = session_type(
            float(configuration.get("session_idle_timeout_seconds", 1800))
        )
        authorization = authorization_type(enabled=enabled)
        if not enabled:
            repository = repository_type(
                project_root / ".security-disabled-unused.db"
            )
            hasher = hasher_type(PasswordPolicy())
            authentication = authentication_type(repository, hasher)
            return SecurityComponents(
                False,
                False,
                False,
                repository,
                hasher,
                authentication,
                sessions,
                authorization,
            )
        configured = Path(
            str(
                configuration.get(
                    "database_path", "data/fastvision/users.db"
                )
            )
        )
        if configured.is_absolute() or ".." in configured.parts:
            raise ValueError(
                "security database path must be project-relative and safe"
            )
        root = project_root.resolve()
        database = (root / configured).resolve()
        if root not in database.parents:
            raise ValueError("security database path escapes project root")
        repository = repository_type(database)
        appliance = configuration.get("appliance_mode", False)
        if type(appliance) is not bool:
            raise ValueError("security.appliance_mode must be boolean")
        if not appliance:
            repository.initialize()
        password_policy = PasswordPolicy(
            int(configuration.get("minimum_password_length", 10)),
            int(configuration.get("maximum_password_length", 128)),
        )
        hasher = hasher_type(password_policy)
        authentication = authentication_type(
            repository,
            hasher,
            AuthenticationPolicy(
                int(configuration.get("max_failed_attempts", 5)),
                int(configuration.get("lockout_seconds", 300)),
            ),
        )
        return SecurityComponents(
            True,
            bool(configuration.get("bootstrap_admin_enabled", True)),
            appliance,
            repository,
            hasher,
            authentication,
            sessions,
            authorization,
        )
