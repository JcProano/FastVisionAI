"""Independent local authentication and RBAC bounded context."""

from .application import *
from .authentication import AuthenticationService
from .authorization import AuthorizationEngine
from .domain import *
from .infrastructure import (
    InMemoryAuthenticatedSessionManager,
    SQLiteUserRepository,
    ScryptPasswordHasher,
)

# Temporary compatibility names used by composition and historical tests.
AuthenticatedSessionManager = InMemoryAuthenticatedSessionManager
PasswordHasher = ScryptPasswordHasher
UserRepository = SQLiteUserRepository
