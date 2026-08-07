from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.engine.enrollment import EnrollmentPolicy, EnrollmentService
from src.engine.gallery import FaceGallery
from src.ui.enrollment_workflow import LocalEnrollmentWorkflow
from src.ui.form_validation import validate_registration_form
from src.ui.main import build_persistence
from tests.test_face_gallery import GalleryTestCase


class UIMainPersistenceTests(GalleryTestCase):
    @staticmethod
    def settings(directory: str = "data/ui_validation") -> dict[str, object]:
        return {"persistence": {"enabled_by_default": False, "directory": directory}}

    def test_paths_are_resolved_from_project_root_without_creating_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            callback, manifest, archive = build_persistence(self.settings(), root)
            self.assertTrue(callable(callback))
            self.assertEqual(manifest, root / "data/ui_validation/gallery.json")
            self.assertEqual(archive, root / "data/ui_validation/gallery.npz")
            self.assertFalse(manifest.parent.exists())

    def test_unchecked_checkbox_does_not_call_or_create_persistence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            callback, manifest, archive = build_persistence(self.settings(), root)
            gallery = FaceGallery()
            workflow = LocalEnrollmentWorkflow(
                gallery, EnrollmentService(gallery, EnrollmentPolicy(1, 1)), 1
            )
            form = validate_registration_form(
                "Temporary", "Person", None, consent_confirmed=True,
                persist_locally=False, id_factory=lambda: "unchecked-person",
            )
            workflow.start(form)
            workflow.add_accepted_sample(self.embedding([1, 0]), None, "complete")
            result = workflow.finish(
                persistence=callback, manifest_path=manifest, archive_path=archive
            )
            self.assertIsNone(result.persistence_succeeded)
            self.assertFalse(manifest.parent.exists())

    def test_checked_checkbox_exports_after_enrollment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            callback, manifest, archive = build_persistence(self.settings(), root)
            gallery = FaceGallery()
            workflow = LocalEnrollmentWorkflow(
                gallery, EnrollmentService(gallery, EnrollmentPolicy(1, 1)), 1
            )
            form = validate_registration_form(
                "Temporary", "Person", None, consent_confirmed=True,
                persist_locally=True, id_factory=lambda: "checked-person",
            )
            workflow.start(form)
            workflow.add_accepted_sample(self.embedding([1, 0]), None, "complete")
            result = workflow.finish(
                persistence=callback, manifest_path=manifest, archive_path=archive
            )
            self.assertTrue(result.persistence_succeeded)
            self.assertTrue(manifest.is_file())
            self.assertTrue(archive.is_file())
            self.assertEqual(len(gallery), 1)

    def test_existing_target_is_not_overwritten_and_memory_gallery_remains(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            callback, manifest, archive = build_persistence(self.settings(), root)
            manifest.parent.mkdir(parents=True)
            manifest.write_bytes(b"existing-manifest")
            archive.write_bytes(b"existing-archive")
            gallery = FaceGallery()
            workflow = LocalEnrollmentWorkflow(
                gallery, EnrollmentService(gallery, EnrollmentPolicy(1, 1)), 1
            )
            form = validate_registration_form(
                "Temporary", "Person", None, consent_confirmed=True,
                persist_locally=True, id_factory=lambda: "existing-target-person",
            )
            workflow.start(form)
            workflow.add_accepted_sample(self.embedding([1, 0]), None, "complete")
            result = workflow.finish(
                persistence=callback, manifest_path=manifest, archive_path=archive
            )
            self.assertFalse(result.persistence_succeeded)
            self.assertEqual(manifest.read_bytes(), b"existing-manifest")
            self.assertEqual(archive.read_bytes(), b"existing-archive")
            self.assertEqual(len(gallery), 1)
            self.assertEqual(len(gallery.templates()), 1)

    def test_absolute_or_escaping_directory_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(ValueError):
                build_persistence(self.settings("/absolute"), root)
            with self.assertRaises(ValueError):
                build_persistence(self.settings("../escape"), root)


if __name__ == "__main__":
    unittest.main()
