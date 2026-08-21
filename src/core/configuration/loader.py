"""Compatibility export for the JSON configuration loader adapter."""

from .infrastructure import JSONConfigurationLoader

ConfigurationLoader = JSONConfigurationLoader

__all__ = ["ConfigurationLoader"]
