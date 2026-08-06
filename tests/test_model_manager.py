from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.engine.models.contracts import ModelBackend, ModelKey, ModelSpec, ModelState
from src.engine.models.manager import (
    ModelArtifactNotFoundError,
    ModelManager,
    ModelRegistrationError,
)


class FakeLoader:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.loads = 0
        self.unloads = 0

    def load(self, spec: ModelSpec) -> object:
        self.loads += 1
        if self.fail:
            raise RuntimeError("load failed")
        return {"model": spec.name, "version": spec.version}

    def unload(self, model: object) -> None:
        del model
        self.unloads += 1


class ModelManagerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / "models").mkdir()
        (self.root / "models" / "dummy.bin").write_bytes(b"model")
        self.manager = ModelManager(self.root)
        self.loader = FakeLoader()
        self.manager.register_loader(ModelBackend.ONNX_RUNTIME, self.loader)

    def spec(self, version: str = "1") -> ModelSpec:
        return ModelSpec("dummy", version, ModelBackend.ONNX_RUNTIME, Path("models/dummy.bin"))

    def test_lazy_load_cache_and_unload(self) -> None:
        spec = self.spec()
        self.manager.register(spec)
        self.assertEqual(self.manager.state(spec.key), ModelState.REGISTERED)
        first = self.manager.get_model(spec.key)
        second = self.manager.get_model(spec.key)
        self.assertIs(first, second)
        self.assertEqual(self.loader.loads, 1)
        self.assertEqual(self.manager.state(spec.key), ModelState.LOADED)
        self.assertTrue(self.manager.unload(spec.key))
        self.assertEqual(self.loader.unloads, 1)
        self.assertEqual(self.manager.state(spec.key), ModelState.REGISTERED)
        self.assertEqual(self.manager.metrics().cache_hits, 1)

    def test_versions_are_independent(self) -> None:
        self.manager.register(self.spec("1"))
        self.manager.register(self.spec("2"))
        self.assertEqual(len(self.manager.registered_specs()), 2)

    def test_duplicate_registration_is_rejected(self) -> None:
        self.manager.register(self.spec())
        with self.assertRaises(ModelRegistrationError):
            self.manager.register(self.spec())

    def test_missing_artifact_moves_to_failed(self) -> None:
        spec = ModelSpec("missing", "1", ModelBackend.ONNX_RUNTIME, Path("models/missing.bin"))
        self.manager.register(spec)
        with self.assertRaises(ModelArtifactNotFoundError):
            self.manager.get_model(spec.key)
        self.assertEqual(self.manager.state(spec.key), ModelState.FAILED)

    def test_unknown_model_state_is_unregistered(self) -> None:
        self.assertEqual(self.manager.state(ModelKey("none", "1")), ModelState.UNREGISTERED)

    def test_logical_alias_revision_changes_with_model(self) -> None:
        first, second = self.spec("1"), self.spec("2")
        self.manager.register(first); self.manager.register(second)
        self.manager.set_alias("default", first.key)
        revision = self.manager.alias_revision("default")
        self.assertEqual(self.manager.resolve_alias("default"), first.key)
        self.manager.set_alias("default", second.key)
        self.assertGreater(self.manager.alias_revision("default"), revision)
        self.assertEqual(self.manager.resolve_alias("default"), second.key)


if __name__ == "__main__":
    unittest.main()
