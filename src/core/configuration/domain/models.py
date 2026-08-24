"""Immutable, redacted public configuration contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping


class ConfigurationError(RuntimeError):
    pass


class ConfigurationProfile(str, Enum):
    DEVELOPMENT = "DEVELOPMENT"
    PRODUCTION = "PRODUCTION"
    TESTING = "TESTING"


class ConfigurationImpact(str, Enum):
    HOT_RELOADABLE = "HOT_RELOADABLE"
    RESTART_REQUIRED = "RESTART_REQUIRED"
    IMMUTABLE_AT_RUNTIME = "IMMUTABLE_AT_RUNTIME"


class ValidationSeverity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"


@dataclass(frozen=True, slots=True)
class ConfigurationValidationIssue:
    path: str
    severity: ValidationSeverity
    message: str


@dataclass(frozen=True, slots=True)
class ConfigurationValidationResult:
    valid: bool
    issues: tuple[ConfigurationValidationIssue, ...]

    @property
    def errors(self) -> tuple[ConfigurationValidationIssue, ...]:
        return tuple(
            item
            for item in self.issues
            if item.severity is ValidationSeverity.ERROR
        )

    @property
    def warnings(self) -> tuple[ConfigurationValidationIssue, ...]:
        return tuple(
            item
            for item in self.issues
            if item.severity is ValidationSeverity.WARNING
        )


@dataclass(frozen=True, slots=True)
class ConfigurationSectionDTO:
    name: str
    values: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class ConfigurationSnapshot:
    profile: ConfigurationProfile
    schema_version: int | None
    legacy_configuration: bool
    sections: Mapping[str, Any]
    source_name: str
    valid: bool = True

    def as_mapping(self) -> dict[str, Any]:
        return thaw(self.sections)


@dataclass(frozen=True, slots=True)
class ConfigurationChangeDTO:
    section: str
    field: str
    old_value: Any
    new_value: Any
    impact: ConfigurationImpact


@dataclass(frozen=True, slots=True)
class ConfigurationDiffDTO:
    changes: tuple[ConfigurationChangeDTO, ...]

    @property
    def hot_reloadable(self) -> tuple[ConfigurationChangeDTO, ...]:
        return tuple(
            item
            for item in self.changes
            if item.impact is ConfigurationImpact.HOT_RELOADABLE
        )

    @property
    def restart_required(self) -> tuple[ConfigurationChangeDTO, ...]:
        return tuple(
            item
            for item in self.changes
            if item.impact is ConfigurationImpact.RESTART_REQUIRED
        )

    @property
    def immutable(self) -> tuple[ConfigurationChangeDTO, ...]:
        return tuple(
            item
            for item in self.changes
            if item.impact is ConfigurationImpact.IMMUTABLE_AT_RUNTIME
        )


@dataclass(frozen=True, slots=True)
class ConfigurationOperationResult:
    success: bool
    message: str
    validation: ConfigurationValidationResult | None = None
    diff: ConfigurationDiffDTO | None = None
    warning: str | None = None


def freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType(
            {str(key): freeze(item) for key, item in value.items()}
        )
    if isinstance(value, (list, tuple)):
        return tuple(freeze(item) for item in value)
    return value


def thaw(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw(item) for item in value]
    return value
