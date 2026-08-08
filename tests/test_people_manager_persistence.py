from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.engine.enrollment import EnrollmentPolicy, EnrollmentService
from src.engine.gallery import FaceGallery, FaceIdentity
from src.engine.gallery.persistence import GalleryPersistence
from src.ui.people.controller import PeopleManagerController
from tests.test_face_gallery import GalleryTestCase


class PeoplePersistenceTests(GalleryTestCase):
    def manager(self, gallery, root):
        return PeopleManagerController(
            gallery, EnrollmentService(gallery, EnrollmentPolicy(1, 5)),
            GalleryPersistence(enabled=True), root / "saved.json", root / "saved.npz",
        )

    def gallery(self, person_id="p1"):
        gallery = FaceGallery(); gallery.register_identity(FaceIdentity(
            person_id, "Temporary Person", {"first_name": "Temporary", "last_name": "Person"}
        )); gallery.add_template(person_id, self.embedding([1, 0]))
        return gallery

    def test_save_export_and_failure_keep_memory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); gallery = self.gallery(); manager = self.manager(gallery, root)
            self.assertTrue(manager.save_changes().success)
            before = (root / "saved.json").read_bytes(), (root / "saved.npz").read_bytes()
            failed = manager.save_changes(overwrite_confirmed=False)
            self.assertFalse(failed.success); self.assertEqual(len(gallery), 1)
            self.assertEqual(before, ((root / "saved.json").read_bytes(),
                                      (root / "saved.npz").read_bytes()))
            # A fresh controller can explicitly overwrite after confirmation.
            manager = self.manager(gallery, root)
            self.assertTrue(manager.save_changes(overwrite_confirmed=True).success)

    def test_import_preview_cancel_replace_and_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); active = self.gallery("active")
            imported = self.gallery("imported")
            GalleryPersistence(enabled=True).export(
                imported, root / "import.json", root / "import.npz"
            )
            manager = self.manager(active, root)
            preview = manager.prepare_import(root / "import.json", root / "import.npz")
            self.assertEqual((preview.identity_count, preview.template_count), (1, 1))
            self.assertFalse(manager.confirm_import(confirmed=False).success)
            self.assertEqual(active.list_identities()[0].person_id, "active")

            manager = self.manager(active, root)
            manager.prepare_import(root / "import.json", root / "import.npz")
            self.assertTrue(manager.confirm_import(confirmed=True).success)
            self.assertEqual(active.list_identities()[0].person_id, "imported")

            corrupt_manager = self.manager(active, root)
            (root / "bad.json").write_text("bad", encoding="utf-8")
            (root / "bad.npz").write_bytes(b"bad")
            before = (active.list_identities(), active.templates())
            result = corrupt_manager.prepare_import(root / "bad.json", root / "bad.npz")
            self.assertFalse(result.success)
            self.assertEqual((active.list_identities(), active.templates()), before)


if __name__ == "__main__":
    unittest.main()
