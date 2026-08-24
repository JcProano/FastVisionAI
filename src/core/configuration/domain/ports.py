"""Dependency-inversion ports for configuration lifecycle workflows."""

from pathlib import Path
from typing import Any, Protocol

from .models import (
    ConfigurationProfile,
    ConfigurationSnapshot,
    ConfigurationValidationResult,
)


class ConfigurationValidatorPort(Protocol):
    def validate(
        self, candidate: object, profile: ConfigurationProfile
    ) -> ConfigurationValidationResult: ...


class ConfigurationLoaderPort(Protocol):
    validator: ConfigurationValidatorPort
    def load(
        self, path: Path, profile: ConfigurationProfile
    ) -> ConfigurationSnapshot: ...


class ConfigurationPolicyPort(Protocol):
    def validate(
        self, candidate: object, profile: ConfigurationProfile
    ) -> ConfigurationValidationResult: ...
    def normalize(self, candidate: dict[str, Any]) -> dict[str, Any]: ...
    def redact(self, value: Any, key: str = "") -> Any: ...


class ConfigurationStorePort(Protocol):
    def save(
        self, candidate: dict[str, Any]
    ) -> tuple[ConfigurationSnapshot, str | None]: ...
    def export(
        self,
        value: dict[str, Any],
        destination: Path,
        *,
        overwrite: bool = False,
    ) -> None: ...
