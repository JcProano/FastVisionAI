"""Compatibility export for the scrypt password adapter."""

from .infrastructure import ScryptPasswordHasher

PasswordHasher = ScryptPasswordHasher

__all__ = ["PasswordHasher"]
