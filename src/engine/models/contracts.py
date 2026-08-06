"""Model lifecycle contracts independent from concrete ML runtimes."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Protocol


class ModelBackend(str, Enum):
    PYTORCH = "pytorch"
    ONNX_RUNTIME = "onnx_runtime"
    TENSORRT = "tensorrt"


class ModelState(str, Enum):
    UNREGISTERED = "unregistered"
    REGISTERED = "registered"
    LOADED = "loaded"
    UNLOADING = "unloading"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ModelKey:
    name: str
    version: str


@dataclass(frozen=True, slots=True)
class ModelSpec:
    name: str
    version: str
    backend: ModelBackend
    artifact_path: Path
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> ModelKey:
        return ModelKey(self.name, self.version)


class ModelLoader(Protocol):
    def load(self, spec: ModelSpec) -> object: ...
    def unload(self, model: object) -> None: ...


@dataclass(frozen=True, slots=True)
class ModelManagerMetrics:
    registered_models: int
    loaded_models: int
    load_attempts: int
    cache_hits: int
    unloads: int
    failures: int
