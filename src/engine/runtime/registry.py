from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from src.engine.contracts.detector import InferenceBackend

RuntimeFactory = Callable[[Mapping[str, Any]], InferenceBackend]


class RuntimeRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, RuntimeFactory] = {}

    def register(self, name: str, factory: RuntimeFactory) -> None:
        if not name.strip() or not callable(factory):
            raise ValueError("Runtime name and callable factory are required")
        if name in self._factories:
            raise ValueError(f"Duplicate runtime: {name}")
        self._factories[name] = factory

    def unregister(self, name: str) -> bool:
        return self._factories.pop(name, None) is not None

    def create(self, name: str, settings: Mapping[str, Any] | None = None) -> InferenceBackend:
        try:
            backend = self._factories[name](settings or {})
        except KeyError as exc:
            raise KeyError(f"Unknown runtime: {name}") from exc
        except Exception as exc:
            raise RuntimeError(f"Could not create runtime {name}: {exc}") from exc
        if not isinstance(backend, InferenceBackend):
            raise TypeError(f"Runtime {name} does not implement InferenceBackend")
        return backend

    def registered_names(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))
