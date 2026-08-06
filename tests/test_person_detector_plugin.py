from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from src.camera.frame import Frame
from src.engine.contracts.inference_context import InferenceContext
from src.engine.models.contracts import ModelBackend, ModelSpec
from src.engine.models.manager import ModelManager
from src.engine.plugins.person_detector.loader import LoadedUltralyticsModel
from src.engine.plugins.person_detector.plugin import PersonDetectorPlugin
from src.engine.plugins.services import PluginServices
from src.engine.preprocessor import MinimalPreprocessor


class FakeLoader:
    def __init__(self, model): self.model = model; self.loads = 0; self.unloads = 0
    def load(self, spec: ModelSpec): self.loads += 1; return LoadedUltralyticsModel(self.model, "abc123")
    def unload(self, model): self.unloads += 1


class FakeModel:
    def predict(self, **kwargs):
        self.kwargs = kwargs
        boxes = [
            SimpleNamespace(cls=np.array([0]), conf=np.array([0.9]), xyxy=np.array([[10, 20, 50, 80]])),
            SimpleNamespace(cls=np.array([2]), conf=np.array([0.8]), xyxy=np.array([[1, 1, 5, 5]])),
        ]
        return [SimpleNamespace(boxes=boxes, names={0: "person", 2: "car"})]


class PersonDetectorPluginTests(unittest.TestCase):
    def test_inference_uses_manager_and_normalizes_boxes(self):
        directory = tempfile.TemporaryDirectory(); self.addCleanup(directory.cleanup)
        root = Path(directory.name); weights = root / "yolov8n.pt"; weights.write_bytes(b"weights")
        manager = ModelManager(root)
        plugin = PersonDetectorPlugin({"model_path": "yolov8n.pt", "allowed_classes": [0]}, PluginServices(manager))
        model = FakeModel(); loader = FakeLoader(model)
        manager.register_loader(ModelBackend.PYTORCH, loader)
        image = np.zeros((100, 200, 3), dtype=np.uint8)
        frame = Frame.create(image, sequence_id=1, source_name="test", monotonic_timestamp=0, connection_id=1)
        result = plugin.infer(MinimalPreprocessor().prepare(frame), InferenceContext(run_id="run", device="cpu"))
        self.assertIs(result.frame, frame)
        self.assertEqual(len(result.detections), 1)
        box = result.detections[0].bounding_box
        self.assertTrue(box.normalized)
        self.assertEqual((box.x1, box.y1, box.x2, box.y2), (0.05, 0.2, 0.25, 0.8))
        self.assertEqual(result.attachments["weights_sha256"], "abc123")
        self.assertEqual(loader.loads, 1)
        plugin.release(); self.assertEqual(loader.unloads, 1)


if __name__ == "__main__": unittest.main()
