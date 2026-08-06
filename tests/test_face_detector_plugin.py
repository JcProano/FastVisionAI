from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from src.camera.frame import Frame
from src.engine.contracts.inference_context import InferenceContext
from src.engine.models.contracts import ModelBackend, ModelSpec, ModelState
from src.engine.models.manager import ModelArtifactNotFoundError, ModelManager
from src.engine.plugins.face_detector.loader import LoadedYuNetModel
from src.engine.plugins.face_detector.plugin import FaceDetectorPlugin
from src.engine.plugins.services import PluginServices
from src.engine.preprocessor import MinimalPreprocessor


class FakeYuNetDetector:
    def __init__(self, faces):
        self.faces = faces
        self.input_size = None

    def setInputSize(self, size):
        self.input_size = size

    def detect(self, image):
        return 1, self.faces


class FakeLoader:
    def __init__(self, detector):
        self.detector = detector
        self.loads = 0
        self.unloads = 0

    def load(self, spec: ModelSpec):
        self.loads += 1
        return LoadedYuNetModel(self.detector, "face-sha256")

    def unload(self, model):
        self.unloads += 1
        model.detector = None


def face_row(x=10, y=20, width=40, height=50, confidence=0.9):
    return [x, y, width, height, 15, 25, 40, 25, 28, 38, 18, 55, 42, 55, confidence]


class FaceDetectorPluginTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / "yunet.onnx").write_bytes(b"yunet-weights")
        self.manager = ModelManager(self.root)

    def make_plugin(self, faces):
        plugin = FaceDetectorPlugin(
            {"model_path": "yunet.onnx", "confidence": 0.6},
            PluginServices(self.manager),
        )
        detector = FakeYuNetDetector(faces)
        loader = FakeLoader(detector)
        self.manager.register_loader(ModelBackend.ONNX_RUNTIME, loader)
        return plugin, detector, loader

    def infer(self, plugin, run_id="face-run"):
        image = np.zeros((100, 200, 3), dtype=np.uint8)
        frame = Frame.create(
            image, sequence_id=1, source_name="test", monotonic_timestamp=0, connection_id=1
        )
        result = plugin.infer(
            MinimalPreprocessor().prepare(frame), InferenceContext(run_id=run_id, device="cpu")
        )
        return frame, result

    def test_zero_faces(self):
        plugin, _, _ = self.make_plugin(None)
        _, result = self.infer(plugin)
        self.assertEqual(result.detections, ())
        self.assertEqual(result.attachments["landmarks"], ())

    def test_one_face_preserves_frame_run_id_and_landmarks(self):
        plugin, detector, _ = self.make_plugin(np.array([face_row()], dtype=np.float32))
        frame, result = self.infer(plugin, "correlation-1")
        self.assertIs(result.frame, frame)
        self.assertEqual(result.attachments["run_id"], "correlation-1")
        self.assertEqual(result.attachments["weights_sha256"], "face-sha256")
        self.assertEqual(detector.input_size, (200, 100))
        self.assertEqual(len(result.detections), 1)
        self.assertEqual(len(result.attachments["landmarks"]), 1)
        self.assertEqual(len(result.attachments["landmarks"][0]), 5)

    def test_multiple_faces(self):
        plugin, _, _ = self.make_plugin(
            np.array([face_row(), face_row(100, 10, 30, 30, 0.8)], dtype=np.float32)
        )
        _, result = self.infer(plugin)
        self.assertEqual(len(result.detections), 2)
        self.assertTrue(all(item.class_name == "face" for item in result.detections))

    def test_boxes_and_landmarks_are_clamped_and_normalized(self):
        plugin, _, _ = self.make_plugin(
            np.array([face_row(-20, -10, 250, 130)], dtype=np.float32)
        )
        _, result = self.infer(plugin)
        box = result.detections[0].bounding_box
        self.assertTrue(box.normalized)
        self.assertEqual((box.x1, box.y1, box.x2, box.y2), (0.0, 0.0, 1.0, 1.0))
        for point in result.attachments["landmarks"][0]:
            self.assertTrue(all(0.0 <= coordinate <= 1.0 for coordinate in point))

    def test_loading_is_lazy_cached_and_released(self):
        plugin, _, loader = self.make_plugin(np.array([face_row()], dtype=np.float32))
        key = self.manager.resolve_alias(plugin.alias)
        self.assertEqual(self.manager.state(key), ModelState.REGISTERED)
        self.assertEqual(loader.loads, 0)
        self.infer(plugin)
        self.infer(plugin)
        self.assertEqual(loader.loads, 1)
        self.assertEqual(self.manager.metrics().cache_hits, 1)
        plugin.release()
        self.assertEqual(loader.unloads, 1)
        self.assertEqual(self.manager.state(key), ModelState.REGISTERED)

    def test_missing_model_is_reported_at_lazy_load(self):
        manager = ModelManager(self.root)
        plugin = FaceDetectorPlugin(
            {"model_path": "missing.onnx"}, PluginServices(manager)
        )
        image = np.zeros((10, 10, 3), dtype=np.uint8)
        frame = Frame.create(
            image, sequence_id=1, source_name="test", monotonic_timestamp=0, connection_id=1
        )
        with self.assertRaises(ModelArtifactNotFoundError):
            plugin.infer(MinimalPreprocessor().prepare(frame), InferenceContext())


if __name__ == "__main__":
    unittest.main()
