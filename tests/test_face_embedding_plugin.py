from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np

from src.camera.frame import Frame
from src.engine.alignment import AlignedFace, AlignmentQuality, AlignmentStatus
from src.engine.contracts.detection import BoundingBox
from src.engine.embedding.loader import LoadedArcFaceModel
from src.engine.embedding.plugin import (
    FaceEmbeddingPlugin,
    InvalidAlignedFaceError,
    InvalidEmbeddingError,
)
from src.engine.models.contracts import ModelBackend, ModelSpec, ModelState
from src.engine.models.manager import ModelArtifactNotFoundError, ModelManager


class FakeNetwork:
    def __init__(self, output):
        self.output = np.asarray(output)
        self.inputs = []

    def setInput(self, value):
        self.inputs.append(value.copy())

    def forward(self):
        return self.output.copy()


class FakeLoader:
    def __init__(self, network):
        self.network = network
        self.loads = 0
        self.unloads = 0

    def load(self, spec: ModelSpec):
        self.loads += 1
        return LoadedArcFaceModel(self.network, "embedding-sha256", 2.5)

    def unload(self, model):
        self.unloads += 1
        model.network = None


class FaceEmbeddingPluginTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        (self.root / "arcface.onnx").write_bytes(b"weights")
        self.manager = ModelManager(self.root)
        image = np.full((112, 112, 3), (10, 20, 30), dtype=np.uint8)
        self.frame = Frame.create(
            image, sequence_id=1, source_name="aligned", monotonic_timestamp=0, connection_id=1
        )

    def make_plugin(self, output=None, **overrides):
        settings = {
            "model_path": "arcface.onnx",
            "embedding_dimension": 4,
            "input_width": 112,
            "input_height": 112,
            "source_color": "BGR",
            "model_color": "RGB",
            "scale": 1.0,
            "mean": [10.0, 20.0, 30.0],
            "std": [2.0, 4.0, 5.0],
            "layout": "NCHW",
        }
        settings.update(overrides)
        plugin = FaceEmbeddingPlugin(settings, self.manager)
        network = FakeNetwork([1.0, 2.0, 3.0, 4.0] if output is None else output)
        loader = FakeLoader(network)
        self.manager.register_loader(ModelBackend.ONNX_RUNTIME, loader)
        return plugin, network, loader

    def aligned_face(
        self,
        *,
        index=0,
        quality=AlignmentQuality.VALID,
        status=AlignmentStatus.ALIGNED,
        image=None,
        run_id="embedding-run",
    ):
        aligned_image = self.frame.image.copy() if image is None else image
        if status is AlignmentStatus.REJECTED:
            aligned_image = None
        return AlignedFace(
            self.frame, aligned_image, BoundingBox(0.1, 0.1, 0.9, 0.9, True),
            ((0.3, 0.35), (0.7, 0.35), (0.5, 0.55), (0.35, 0.75), (0.65, 0.75)),
            np.eye(2, 3), np.eye(2, 3), index, 0.9, run_id, status,
            quality if status is AlignmentStatus.ALIGNED else AlignmentQuality.REJECTED,
            None if status is AlignmentStatus.ALIGNED else "rejected", 1.0, 0.2, 0.3, 1.0,
        )

    def test_embedding_is_deterministic_normalized_and_read_only(self):
        plugin, _, _ = self.make_plugin()
        first = plugin.embed((self.aligned_face(),))[0]
        second = plugin.embed((self.aligned_face(),))[0]
        self.assertTrue(np.array_equal(first.embedding, second.embedding))
        self.assertEqual(first.embedding.dtype, np.float32)
        self.assertEqual(first.dimension, 4)
        self.assertAlmostEqual(first.l2_norm, 1.0, places=6)
        self.assertFalse(first.embedding.flags.writeable)
        self.assertAlmostEqual(
            plugin.diagnostic_pre_normalization_norm(first.run_id, first.face_index),
            np.linalg.norm(np.array([1, 2, 3, 4], dtype=np.float32)),
        )
        with self.assertRaises(ValueError):
            first.embedding[0] = 0

    def test_preprocessing_is_explicit_rgb_nchw_mean_std_and_scale(self):
        plugin, network, _ = self.make_plugin(scale=2.0)
        plugin.embed((self.aligned_face(),))
        blob = network.inputs[0]
        self.assertEqual(blob.shape, (1, 3, 112, 112))
        # BGR (10,20,30) -> RGB (30,20,10), then (x-mean)/std*scale.
        self.assertTrue(np.allclose(blob[0, :, 0, 0], (20.0, 0.0, -8.0)))

    def test_multiple_faces_preserve_frame_run_id_index_and_quality(self):
        plugin, _, _ = self.make_plugin()
        outputs = plugin.embed((
            self.aligned_face(index=3, run_id="r3"),
            self.aligned_face(index=8, run_id="r8", quality=AlignmentQuality.LOW_QUALITY),
        ))
        self.assertEqual([item.face_index for item in outputs], [3, 8])
        self.assertEqual([item.run_id for item in outputs], ["r3", "r8"])
        self.assertTrue(all(item.frame is self.frame for item in outputs))
        self.assertEqual(outputs[1].alignment_quality, AlignmentQuality.LOW_QUALITY)
        metrics = plugin.metrics()
        self.assertEqual(metrics.embeddings_generated, 2)
        self.assertEqual(metrics.low_quality_embeddings, 1)

    def test_rejected_face_is_skipped_without_loading_or_error(self):
        plugin, _, loader = self.make_plugin()
        outputs = plugin.embed((self.aligned_face(status=AlignmentStatus.REJECTED),))
        self.assertEqual(outputs, ())
        self.assertEqual(loader.loads, 0)
        metrics = plugin.metrics()
        self.assertEqual(metrics.faces_skipped, 1)
        self.assertEqual(metrics.errors, 0)

    def test_wrong_image_size_is_typed_error(self):
        plugin, _, _ = self.make_plugin()
        with self.assertRaises(InvalidAlignedFaceError):
            plugin.embed((self.aligned_face(image=np.zeros((111, 112, 3), dtype=np.uint8)),))

    def test_zero_norm_is_rejected(self):
        plugin, _, _ = self.make_plugin(output=np.zeros(4, dtype=np.float32))
        with self.assertRaises(InvalidEmbeddingError):
            plugin.embed((self.aligned_face(),))

    def test_nan_and_infinity_are_rejected(self):
        for value in (np.nan, np.inf):
            manager = ModelManager(self.root)
            self.manager = manager
            plugin, _, _ = self.make_plugin(output=[1, 2, 3, value])
            with self.assertRaises(InvalidEmbeddingError):
                plugin.embed((self.aligned_face(),))

    def test_wrong_embedding_dimension_is_rejected(self):
        plugin, _, _ = self.make_plugin(output=[1, 2, 3])
        with self.assertRaises(InvalidEmbeddingError):
            plugin.embed((self.aligned_face(),))

    def test_lazy_loading_cache_and_release(self):
        plugin, _, loader = self.make_plugin()
        key = self.manager.resolve_alias(plugin.alias)
        self.assertEqual(self.manager.state(key), ModelState.REGISTERED)
        self.assertEqual(loader.loads, 0)
        plugin.embed((self.aligned_face(),))
        plugin.embed((self.aligned_face(),))
        self.assertEqual(loader.loads, 1)
        self.assertEqual(self.manager.metrics().cache_hits, 1)
        self.assertEqual(plugin.metrics().model_load_time_ms, 2.5)
        plugin.release()
        self.assertEqual(loader.unloads, 1)
        self.assertEqual(self.manager.state(key), ModelState.REGISTERED)

    def test_missing_model_fails_only_when_embedding_is_requested(self):
        manager = ModelManager(self.root)
        plugin = FaceEmbeddingPlugin(
            {"model_path": "missing.onnx", "embedding_dimension": 4}, manager
        )
        self.assertEqual(manager.metrics().load_attempts, 0)
        with self.assertRaises(ModelArtifactNotFoundError):
            plugin.embed((self.aligned_face(),))


if __name__ == "__main__":
    unittest.main()
