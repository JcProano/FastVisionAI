from __future__ import annotations

import unittest
import tempfile
from pathlib import Path

from src.engine.contracts.detector import InferenceBackend
from src.engine.plugins.manager import PluginManager, PluginValidationError
from src.engine.plugins.services import PluginServices
from src.engine.models.manager import ModelManager


class PluginManagerTests(unittest.TestCase):
    def manager(self) -> PluginManager:
        return PluginManager(PluginServices(ModelManager(Path(tempfile.gettempdir()))))

    def test_discovers_descriptor_and_loads_enabled_plugin_lazily(self) -> None:
        manager = self.manager()
        descriptors = manager.discover()
        self.assertGreaterEqual(len(descriptors), 2)
        descriptor = next(item for item in descriptors if item.id == "dummy")
        self.assertEqual(descriptor.id, "dummy")
        self.assertEqual(descriptor.author, "FastVisionAI")
        self.assertIn("detection", {item.id for item in descriptor.capabilities})
        self.assertFalse(descriptor.enabled)

        manager.configure({"dummy": {"detection_count": 2}}, {"dummy": 5})
        loaded = manager.load_enabled()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0].descriptor.priority, 5)
        self.assertTrue(loaded[0].descriptor.enabled)
        self.assertIsInstance(loaded[0].backend, InferenceBackend)
        self.assertIs(manager.load_enabled()[0].backend, loaded[0].backend)

    def test_disabled_plugin_is_not_loaded(self) -> None:
        manager = self.manager()
        manager.discover()
        manager.configure({})
        self.assertEqual(manager.load_enabled(), ())

    def test_unknown_plugin_configuration_is_rejected(self) -> None:
        manager = self.manager()
        manager.discover()
        with self.assertRaises(PluginValidationError):
            manager.configure({"unknown": {}})


if __name__ == "__main__":
    unittest.main()
