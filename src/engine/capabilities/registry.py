from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.engine.plugins.contracts import PluginDescriptor


class CapabilitiesRegistry:
    def __init__(self) -> None:
        self._plugins: dict[str, PluginDescriptor] = {}

    def register(self, descriptor: PluginDescriptor) -> None:
        if descriptor.id in self._plugins:
            raise ValueError(f"Duplicate plugin capabilities: {descriptor.id}")
        ids = [capability.id for capability in descriptor.capabilities]
        if len(ids) != len(set(ids)):
            raise ValueError(f"Duplicate capabilities in plugin: {descriptor.id}")
        self._plugins[descriptor.id] = descriptor

    def unregister(self, plugin_id: str) -> bool:
        return self._plugins.pop(plugin_id, None) is not None

    def find_by_capability(
        self, capability_id: str, include_disabled: bool = False
    ) -> tuple[PluginDescriptor, ...]:
        return tuple(sorted(
            (
                descriptor for descriptor in self._plugins.values()
                if (include_disabled or descriptor.enabled)
                and any(item.id == capability_id for item in descriptor.capabilities)
            ),
            key=lambda item: (item.priority, item.id),
        ))

    def capabilities(self):
        unique = {item.id: item for descriptor in self._plugins.values() for item in descriptor.capabilities}
        return tuple(unique[key] for key in sorted(unique))
