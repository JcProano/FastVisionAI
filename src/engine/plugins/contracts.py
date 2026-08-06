"""Plugin metadata; execution remains exclusively InferenceBackend."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Callable, Mapping

from src.engine.capabilities.contracts import Capability
from src.engine.contracts.detector import InferenceBackend
from src.engine.plugins.services import PluginServices


@dataclass(frozen=True, slots=True)
class PluginDescriptor:
    id: str
    name: str
    version: str
    api_version: str
    author: str
    description: str
    backend: str
    capabilities: tuple[Capability, ...]
    priority: int
    enabled: bool = False

    def with_enabled(self, enabled: bool) -> PluginDescriptor:
        return replace(self, enabled=enabled)


PluginFactory = Callable[[Mapping[str, Any], PluginServices], InferenceBackend]


@dataclass(frozen=True, slots=True)
class LoadedPlugin:
    descriptor: PluginDescriptor
    backend: InferenceBackend
