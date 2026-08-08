import dataclasses
import json
import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from src.engine.gallery import FaceGallery
from src.engine.gallery.persistence import GalleryPersistence
from src.engine.recognition.contracts import RecognitionResult
from src.ui.main import build_thumbnail_manager
from src.ui.mock_runtime import MockUIRuntimeAdapter
from src.engine.capture_quality import CapturePose
from src.ui.thumbnails import ThumbnailExistsError, ThumbnailManager, select_thumbnail
from src.ui.thumbnails.contracts import ThumbnailDTO, ThumbnailSample


def image_bytes(value: int = 100) -> bytes:
    ok, payload = cv2.imencode(".png", np.full((112, 112, 3), value, np.uint8))
    assert ok
    return payload.tobytes()


class ThumbnailManagerTests(unittest.TestCase):
    def test_disabled_does_not_create_or_write(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manager = ThumbnailManager(root, Path("visual"), enabled=False)
            result = manager.save("person_safe", image_bytes())
            self.assertFalse(result.available)
            self.assertFalse((root / "visual").exists())
        adapter = MockUIRuntimeAdapter(delay=0, thumbnail_capture_enabled=False)
        adapter.set_thumbnail_capture(True)
        self.assertIsNone(adapter.process(CapturePose.FRONTAL).aligned_face_bytes)

    def test_deterministic_frontal_selection_fallback_and_tie(self):
        payload = image_bytes()
        samples = (
            ThumbnailSample(0, "slight_left", 99, payload),
            ThumbnailSample(2, "frontal", 90, payload),
            ThumbnailSample(1, "frontal", 90, payload),
        )
        self.assertEqual(select_thumbnail(samples).sample_index, 1)
        fallback = samples[:1]
        self.assertEqual(select_thumbnail(fallback).sample_index, 0)

    def test_safe_atomic_save_load_replace_delete_and_dimensions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manager = ThumbnailManager(root, Path("visual"), width=64, height=48)
            result = manager.save("person_safe", image_bytes())
            self.assertEqual((result.width, result.height), (64, 48))
            self.assertTrue(result.available)
            self.assertNotIn("path", {field.name for field in dataclasses.fields(result)})
            with self.assertRaises(ThumbnailExistsError):
                manager.save("person_safe", image_bytes(120))
            manager.save("person_safe", image_bytes(120), replace=True)
            self.assertTrue(manager.delete("person_safe"))
            self.assertFalse(manager.load("person_safe").available)

    def test_traversal_invalid_format_and_manual_invalid_image(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with self.assertRaises(ValueError):
                ThumbnailManager(root, Path("visual"), image_format="gif")
            manager = ThumbnailManager(root, Path("visual"))
            for unsafe in ("../person", "a/b", "..", "person name"):
                with self.assertRaises(ValueError):
                    manager.load(unsafe)
            with self.assertRaises(Exception):
                manager.save("person_safe", b"not-an-image")

    def test_builder_is_relative_and_gallery_persistence_has_no_thumbnail(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            settings = {"thumbnails": {"enabled": True, "directory": "visual"}}
            manager = build_thumbnail_manager(settings, root)
            self.assertFalse(manager.load("person_old").available)
            gallery = FaceGallery()
            manifest, archive = root / "gallery.json", root / "gallery.npz"
            GalleryPersistence(enabled=True).export(gallery, manifest, archive)
            self.assertNotIn("thumbnail", manifest.read_text(encoding="utf-8").casefold())
            with np.load(archive, allow_pickle=False) as data:
                self.assertTrue(all("thumbnail" not in key.casefold() for key in data.files))

    def test_public_contracts_do_not_embed_thumbnail_into_recognition(self):
        fields = {field.name for field in dataclasses.fields(RecognitionResult)}
        self.assertNotIn("thumbnail", fields)
        dto_fields = {field.name for field in dataclasses.fields(ThumbnailDTO)}
        self.assertEqual(dto_fields, {
            "person_id", "available", "width", "height", "format", "image_bytes",
        })


if __name__ == "__main__":
    unittest.main()
