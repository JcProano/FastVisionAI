from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.engine.gallery import FaceGallery, FaceIdentity
from src.engine.gallery.persistence import (
    GalleryPersistence, GalleryPersistenceError, PersistenceDisabledError,
)
from tests.test_face_gallery import GalleryTestCase


class FaceGalleryPersistenceTests(GalleryTestCase):
    def setUp(self):
        super().setUp()
        directory = tempfile.TemporaryDirectory(); self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def populated(self):
        gallery = FaceGallery(); gallery.register_identity(FaceIdentity("a", "Temporary A"))
        gallery.add_template("a", self.embedding([1, 2, 3]), "synthetic")
        return gallery

    def test_persistence_is_disabled_by_default(self):
        with self.assertRaises(PersistenceDisabledError):
            GalleryPersistence().export(
                self.populated(), self.root / "gallery.json", self.root / "gallery.npz"
            )

    def test_export_import_round_trip(self):
        manifest, archive = self.root / "gallery.json", self.root / "gallery.npz"
        persistence = GalleryPersistence(enabled=True)
        persistence.export(self.populated(), manifest, archive)
        imported = FaceGallery()
        persistence.import_into(imported, manifest, archive)
        self.assertEqual([item.person_id for item in imported.list_identities()], ["a"])
        self.assertEqual(len(imported.templates()), 1)
        self.assertNotIn("embedding", manifest.read_text(encoding="utf-8"))

    def test_failed_import_is_transactional(self):
        manifest, archive = self.root / "gallery.json", self.root / "gallery.npz"
        persistence = GalleryPersistence(enabled=True)
        persistence.export(self.populated(), manifest, archive)
        active = FaceGallery(); active.register_identity(FaceIdentity("keep", "Keep"))
        with archive.open("ab") as stream:
            stream.write(b"tampered")
        with self.assertRaises(GalleryPersistenceError):
            persistence.import_into(active, manifest, archive)
        self.assertEqual([item.person_id for item in active.list_identities()], ["keep"])
        self.assertEqual(active.templates(), ())


if __name__ == "__main__": unittest.main()
