from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.engine.gallery import FaceIdentity, FaceMatcher, MatchPolicy
from src.engine.gallery.persistence import GalleryPersistence
from src.ui.contracts import UIErrorCode
from src.ui.main import load_startup_gallery
from tests.test_face_gallery import GalleryTestCase


class UIStartupGalleryTests(GalleryTestCase):
    @staticmethod
    def settings(load: bool, directory: str = "gallery") -> dict[str, object]:
        return {"persistence": {
            "enabled_by_default": False,
            "load_on_startup": load,
            "directory": directory,
        }}

    def create_valid_gallery(self, root: Path) -> None:
        from src.engine.gallery import FaceGallery
        gallery = FaceGallery()
        gallery.register_identity(FaceIdentity("temporary", "Temporary"))
        gallery.add_template("temporary", self.embedding([1, 0]))
        destination = root / "gallery"
        GalleryPersistence(enabled=True).export(
            gallery, destination / "gallery.json", destination / "gallery.npz"
        )

    def test_startup_without_load_does_not_access_persistence_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch("pathlib.Path.is_file", side_effect=AssertionError("unexpected access")):
                result = load_startup_gallery(self.settings(False), project_root=root)
            self.assertEqual(len(result.gallery), 0)
            self.assertEqual(result.message, "Galería vacía")
            self.assertIsNone(result.error)

    def test_force_load_overrides_disabled_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.create_valid_gallery(root)
            result = load_startup_gallery(
                self.settings(False), force_load=True, project_root=root
            )
            self.assertEqual(len(result.gallery), 1)

    def test_valid_gallery_loads_and_is_immediately_matchable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); self.create_valid_gallery(root)
            result = load_startup_gallery(self.settings(True), project_root=root)
            self.assertEqual(result.message, "Galería cargada: 1 identidades, 1 templates")
            match = FaceMatcher(policy=MatchPolicy(False, None)).match(
                self.embedding([1, 0]), result.gallery
            )
            self.assertEqual(match.best_candidate.identity.person_id, "temporary")
            self.assertEqual(match.decision.value, "not_evaluated")

    def test_both_files_missing_is_informational(self):
        with tempfile.TemporaryDirectory() as directory:
            result = load_startup_gallery(
                self.settings(True), project_root=Path(directory)
            )
            self.assertEqual(len(result.gallery), 0)
            self.assertIsNone(result.error)
            self.assertEqual(result.message, "Galería vacía")

    def test_manifest_without_npz_and_npz_without_manifest_are_safe_errors(self):
        for filename in ("gallery.json", "gallery.npz"):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); target = root / "gallery"
                target.mkdir(); (target / filename).write_bytes(b"incomplete")
                result = load_startup_gallery(self.settings(True), project_root=root)
                self.assertEqual(len(result.gallery), 0)
                self.assertEqual(result.error.operation, UIErrorCode.PERSISTENCE_ERROR)

    def test_corrupt_files_leave_gallery_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); target = root / "gallery"
            target.mkdir()
            (target / "gallery.json").write_text("not-json", encoding="utf-8")
            (target / "gallery.npz").write_bytes(b"not-npz")
            result = load_startup_gallery(self.settings(True), project_root=root)
            self.assertEqual(len(result.gallery), 0)
            self.assertEqual(result.error.operation, UIErrorCode.PERSISTENCE_ERROR)
            self.assertNotIn("not-json", result.error.message)


if __name__ == "__main__":
    unittest.main()
