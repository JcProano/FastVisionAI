"""Thread-safe lazy model registry and cache."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from pathlib import Path

from src.engine.models.contracts import (
    ModelBackend,
    ModelKey,
    ModelLoader,
    ModelManagerMetrics,
    ModelSpec,
    ModelState,
)

LOGGER = logging.getLogger(__name__)


class ModelManagerError(RuntimeError):
    pass


class ModelRegistrationError(ModelManagerError):
    pass


class ModelNotFoundError(ModelManagerError):
    pass


class ModelArtifactNotFoundError(ModelManagerError):
    pass


class ModelLoadError(ModelManagerError):
    pass


@dataclass(slots=True)
class _ModelEntry:
    spec: ModelSpec
    state: ModelState = ModelState.REGISTERED
    instance: object | None = None


class ModelManager:
    def __init__(self, project_root: Path) -> None:
        self._project_root = project_root.resolve()
        self._entries: dict[ModelKey, _ModelEntry] = {}
        self._aliases: dict[str, ModelKey] = {}
        self._alias_revisions: dict[str, int] = {}
        self._loaders: dict[ModelBackend, ModelLoader] = {}
        self._lock = threading.RLock()
        self._load_attempts = 0
        self._cache_hits = 0
        self._unloads = 0
        self._failures = 0

    def register_loader(self, backend: ModelBackend, loader: ModelLoader) -> None:
        with self._lock:
            self._loaders[backend] = loader

    def register(self, spec: ModelSpec) -> None:
        with self._lock:
            if spec.key in self._entries:
                raise ModelRegistrationError(f"Model already registered: {spec.key}")
            resolved = self._resolve_artifact(spec.artifact_path)
            normalized = ModelSpec(
                name=spec.name,
                version=spec.version,
                backend=spec.backend,
                artifact_path=resolved,
                metadata=dict(spec.metadata),
            )
            self._entries[spec.key] = _ModelEntry(normalized)

    def exists(self, key: ModelKey) -> bool:
        with self._lock:
            return key in self._entries

    def set_alias(self, alias: str, key: ModelKey) -> None:
        if not alias.strip():
            raise ValueError("Model alias must be non-empty")
        with self._lock:
            self._entry(key)
            if self._aliases.get(alias) != key:
                self._aliases[alias] = key
                self._alias_revisions[alias] = self._alias_revisions.get(alias, 0) + 1

    def resolve_alias(self, alias: str) -> ModelKey:
        with self._lock:
            try:
                return self._aliases[alias]
            except KeyError as exc:
                raise ModelNotFoundError(f"Unknown model alias: {alias}") from exc

    def alias_revision(self, alias: str) -> int:
        with self._lock:
            return self._alias_revisions.get(alias, 0)

    def get_model_by_alias(self, alias: str) -> object:
        return self.get_model(self.resolve_alias(alias))

    def state(self, key: ModelKey) -> ModelState:
        with self._lock:
            entry = self._entries.get(key)
            return ModelState.UNREGISTERED if entry is None else entry.state

    def get_model(self, key: ModelKey) -> object:
        with self._lock:
            entry = self._entry(key)
            if entry.state is ModelState.LOADED and entry.instance is not None:
                self._cache_hits += 1
                return entry.instance
            if not entry.spec.artifact_path.is_file():
                entry.state = ModelState.FAILED
                self._failures += 1
                raise ModelArtifactNotFoundError(str(entry.spec.artifact_path))
            loader = self._loaders.get(entry.spec.backend)
            if loader is None:
                entry.state = ModelState.FAILED
                self._failures += 1
                raise ModelLoadError(f"No loader registered for {entry.spec.backend.value}")
            self._load_attempts += 1
            try:
                entry.instance = loader.load(entry.spec)
            except Exception as exc:
                entry.state = ModelState.FAILED
                self._failures += 1
                raise ModelLoadError(f"Could not load {key}: {exc}") from exc
            entry.state = ModelState.LOADED
            return entry.instance

    def unload(self, key: ModelKey) -> bool:
        with self._lock:
            entry = self._entry(key)
            if entry.state is not ModelState.LOADED or entry.instance is None:
                return False
            entry.state = ModelState.UNLOADING
            instance = entry.instance
            loader = self._loaders.get(entry.spec.backend)
            try:
                if loader is not None:
                    loader.unload(instance)
            except Exception as exc:
                entry.state = ModelState.FAILED
                self._failures += 1
                raise ModelManagerError(f"Could not unload {key}: {exc}") from exc
            entry.instance = None
            entry.state = ModelState.REGISTERED
            self._unloads += 1
            return True

    def unload_all(self) -> None:
        with self._lock:
            keys = [key for key, entry in self._entries.items() if entry.state is ModelState.LOADED]
        for key in keys:
            self.unload(key)

    def registered_specs(self) -> tuple[ModelSpec, ...]:
        with self._lock:
            return tuple(entry.spec for entry in self._entries.values())

    def metrics(self) -> ModelManagerMetrics:
        with self._lock:
            return ModelManagerMetrics(
                registered_models=len(self._entries),
                loaded_models=sum(entry.state is ModelState.LOADED for entry in self._entries.values()),
                load_attempts=self._load_attempts,
                cache_hits=self._cache_hits,
                unloads=self._unloads,
                failures=self._failures,
            )

    def _entry(self, key: ModelKey) -> _ModelEntry:
        try:
            return self._entries[key]
        except KeyError as exc:
            raise ModelNotFoundError(str(key)) from exc

    def _resolve_artifact(self, path: Path) -> Path:
        return path.resolve() if path.is_absolute() else (self._project_root / path).resolve()
