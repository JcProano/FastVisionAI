"""Compatibility export for the in-memory authenticated session adapter."""

from .infrastructure import InMemoryAuthenticatedSessionManager

AuthenticatedSessionManager = InMemoryAuthenticatedSessionManager

__all__ = ["AuthenticatedSessionManager"]
