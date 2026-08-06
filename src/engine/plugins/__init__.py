"""Plugin discovery and built-in inference plugins."""

from src.engine.plugins.contracts import PluginDescriptor
from src.engine.plugins.manager import PluginManager

__all__ = ["PluginDescriptor", "PluginManager"]
