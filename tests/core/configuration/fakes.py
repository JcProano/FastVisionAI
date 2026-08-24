"""Test doubles for configuration application ports."""

from __future__ import annotations

from pathlib import Path

from src.core.configuration.domain import (
    ConfigurationProfile,
    ConfigurationSnapshot,
    ConfigurationValidationResult,
    freeze,
)


def snapshot(value=None, source="config.json") -> ConfigurationSnapshot:
    data = value or {"config_schema_version": 1}
    return ConfigurationSnapshot(
        ConfigurationProfile.DEVELOPMENT,
        data.get("config_schema_version"),
        "config_schema_version" not in data,
        freeze(data),
        source,
    )


class FakePolicy:
    def __init__(self, valid=True) -> None:
        self.valid = valid

    def validate(self, candidate, profile):
        del candidate, profile
        return ConfigurationValidationResult(self.valid, ())

    def normalize(self, candidate):
        return dict(candidate)

    def redact(self, value, key=""):
        if "secret" in key:
            return "[REDACTED]"
        if isinstance(value, dict):
            return {
                item_key: self.redact(item, item_key)
                for item_key, item in value.items()
            }
        return value


class FakeLoader:
    def __init__(self, loaded=None) -> None:
        self.loaded = loaded or snapshot()
        self.validator = FakePolicy()
        self.paths: list[Path] = []

    def load(self, path, profile):
        del profile
        self.paths.append(path)
        return self.loaded


class FakeStore:
    def __init__(self, saved=None) -> None:
        self.saved = saved or snapshot()
        self.save_calls = []
        self.export_calls = []
        self.fail_save = False

    def save(self, candidate):
        self.save_calls.append(candidate)
        if self.fail_save:
            raise OSError("simulated save failure")
        return self.saved, None

    def export(self, value, destination, *, overwrite=False):
        self.export_calls.append((value, destination, overwrite))
