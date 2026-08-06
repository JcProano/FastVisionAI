"""Discovery, enablement and dynamic loading of trusted Python plugins."""

from __future__ import annotations

import importlib
import importlib.util
import logging
import pkgutil
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping

from src.engine.capabilities.registry import CapabilitiesRegistry
from src.engine.contracts.detector import InferenceBackend
from src.engine.plugins.contracts import LoadedPlugin, PluginDescriptor
from src.engine.plugins.services import PluginServices

LOGGER = logging.getLogger(__name__)


class PluginManagerError(RuntimeError):
    pass


class PluginDiscoveryError(PluginManagerError):
    pass


class PluginLoadError(PluginManagerError):
    pass


class PluginValidationError(PluginManagerError):
    pass


@dataclass(slots=True)
class _PluginEntry:
    descriptor: PluginDescriptor
    module: ModuleType
    settings: Mapping[str, Any]
    instance: InferenceBackend | None = None


class PluginManager:
    def __init__(self, services: PluginServices, external_directories: tuple[Path, ...] = (), capabilities: CapabilitiesRegistry | None = None) -> None:
        self._services = services
        self._external_directories = external_directories
        self._entries: dict[str, _PluginEntry] = {}
        self._capabilities = capabilities

    def discover(self) -> tuple[PluginDescriptor, ...]:
        builtin_directory = Path(__file__).resolve().parent
        infrastructure_modules = {"contracts", "manager", "services"}
        for module_info in pkgutil.iter_modules([str(builtin_directory)]):
            if module_info.name.startswith("_") or module_info.name in infrastructure_modules:
                continue
            self._discover_module(f"src.engine.plugins.{module_info.name}")
        for directory in self._external_directories:
            if not directory.is_dir():
                continue
            for path in sorted(directory.glob("*.py")):
                if path.name.startswith("_"):
                    continue
                module_name = f"fastvision_external_{path.stem}"
                spec = importlib.util.spec_from_file_location(module_name, path)
                if spec is None or spec.loader is None:
                    raise PluginDiscoveryError(f"Cannot create module spec for {path}")
                module = importlib.util.module_from_spec(spec)
                try:
                    spec.loader.exec_module(module)
                except Exception as exc:
                    raise PluginDiscoveryError(f"Cannot import {path}: {exc}") from exc
                self._register_module(module)
        return self.descriptors()

    def configure(
        self,
        enabled_plugins: Mapping[str, Mapping[str, Any]],
        priorities: Mapping[str, int] | None = None,
    ) -> None:
        priorities = priorities or {}
        unknown = set(enabled_plugins) - set(self._entries)
        if unknown:
            raise PluginValidationError(f"Unknown plugins: {sorted(unknown)}")
        for plugin_id, entry in self._entries.items():
            descriptor = entry.descriptor.with_enabled(plugin_id in enabled_plugins)
            if plugin_id in priorities:
                descriptor = PluginDescriptor(
                    id=descriptor.id,
                    name=descriptor.name,
                    version=descriptor.version,
                    api_version=descriptor.api_version,
                    author=descriptor.author,
                    description=descriptor.description,
                    backend=descriptor.backend,
                    capabilities=descriptor.capabilities,
                    priority=priorities[plugin_id],
                    enabled=descriptor.enabled,
                )
            entry.descriptor = descriptor
            entry.settings = enabled_plugins.get(plugin_id, {})
            if not descriptor.enabled:
                entry.instance = None

    def load_enabled(self) -> tuple[LoadedPlugin, ...]:
        loaded: list[LoadedPlugin] = []
        enabled_entries = sorted(
            (entry for entry in self._entries.values() if entry.descriptor.enabled),
            key=lambda item: (item.descriptor.priority, item.descriptor.id),
        )
        for entry in enabled_entries:
            if entry.instance is None:
                factory = getattr(entry.module, "create_plugin", None)
                if not callable(factory):
                    raise PluginLoadError(f"Plugin {entry.descriptor.id} has no create_plugin factory")
                try:
                    instance = factory(entry.settings, self._services)
                except Exception as exc:
                    raise PluginLoadError(f"Could not load {entry.descriptor.id}: {exc}") from exc
                if not isinstance(instance, InferenceBackend):
                    raise PluginValidationError(
                        f"Plugin {entry.descriptor.id} does not implement InferenceBackend"
                    )
                entry.instance = instance
            loaded.append(LoadedPlugin(entry.descriptor, entry.instance))
        return tuple(loaded)

    def descriptors(self) -> tuple[PluginDescriptor, ...]:
        return tuple(
            sorted(
                (entry.descriptor for entry in self._entries.values()),
                key=lambda item: (item.priority, item.id),
            )
        )

    def unload_all(self) -> None:
        for entry in self._entries.values():
            entry.instance = None

    def _discover_module(self, module_name: str) -> None:
        try:
            module = importlib.import_module(module_name)
        except Exception as exc:
            raise PluginDiscoveryError(f"Cannot import {module_name}: {exc}") from exc
        self._register_module(module)

    def _register_module(self, module: ModuleType) -> None:
        descriptor = getattr(module, "PLUGIN_DESCRIPTOR", None)
        if not isinstance(descriptor, PluginDescriptor):
            raise PluginValidationError(f"Module {module.__name__} has no valid PLUGIN_DESCRIPTOR")
        if descriptor.id in self._entries:
            raise PluginValidationError(f"Duplicate plugin id: {descriptor.id}")
        self._entries[descriptor.id] = _PluginEntry(descriptor, module, {})
        if self._capabilities is not None:
            self._capabilities.register(descriptor)
