from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.engine.enrollment import EnrollmentPolicy, EnrollmentService
from src.engine.gallery import FaceGallery, FaceMatcher, MatchPolicy
from src.ui.controller import LocalFaceUIController
from src.ui.enrollment_workflow import EnrollmentAlreadyActiveError, LocalEnrollmentWorkflow
from src.ui.form_validation import RegistrationFormError, validate_registration_form
from src.ui.recognition_session import ExperimentalRecognitionSession
from tests.test_face_gallery import GalleryTestCase


class UIEnrollmentTests(GalleryTestCase):
    def form(self, *, persist=False):
        return validate_registration_form(
            "Ada", "Lovelace", "internal-optional", consent_confirmed=True,
            persist_locally=persist, id_factory=lambda: "person_generated_123",
        )

    def workflow(self, gallery=None, target=2):
        gallery = gallery or FaceGallery()
        service = EnrollmentService(gallery, EnrollmentPolicy(2, 3))
        return gallery, LocalEnrollmentWorkflow(gallery, service, target)

    def test_form_separates_names_metadata_and_generated_id(self):
        form = self.form()
        self.assertEqual(form.first_name, "Ada")
        self.assertEqual(form.last_name, "Lovelace")
        self.assertEqual(form.display_name, "Ada Lovelace")
        self.assertEqual(form.external_identifier, "internal-optional")
        self.assertNotIn("ada", form.person_id.lower())

    def test_required_names_and_consent(self):
        for first, last, consent in (("", "Last", True), ("First", "", True),
                                     ("First", "Last", False)):
            with self.assertRaises(RegistrationFormError):
                validate_registration_form(first, last, None,
                                           consent_confirmed=consent, persist_locally=False)

    def test_cancel_before_commit_has_no_gallery_effect(self):
        gallery, workflow = self.workflow()
        workflow.start(self.form())
        workflow.add_accepted_sample(self.embedding([1, 0]), None, "frontal")
        workflow.cancel()
        self.assertFalse(workflow.active)
        self.assertEqual(gallery.list_identities(), ())
        self.assertEqual(gallery.templates(), ())

    def test_double_click_is_blocked_and_close_cancels(self):
        gallery, workflow = self.workflow()
        controller = LocalFaceUIController(
            ExperimentalRecognitionSession(gallery, FaceMatcher(policy=MatchPolicy(False, None))),
            workflow,
        )
        controller.begin_enrollment(self.form())
        with self.assertRaises(EnrollmentAlreadyActiveError):
            controller.begin_enrollment(self.form())
        controller.close()
        self.assertFalse(workflow.active)
        self.assertEqual(gallery.list_identities(), ())

    def test_persistence_runs_only_after_success(self):
        gallery, workflow = self.workflow()
        workflow.start(self.form(persist=True))
        workflow.add_accepted_sample(self.embedding([1, 0]), None, "frontal")
        workflow.add_accepted_sample(self.embedding([.8, .2], index=1), None, "left")
        calls = []

        def persist(current, manifest, archive):
            self.assertEqual(len(current), 1)
            calls.append((manifest, archive))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = workflow.finish(
                persistence=persist, manifest_path=root / "gallery.json",
                archive_path=root / "gallery.npz",
            )
        self.assertEqual(len(calls), 1)
        self.assertTrue(result.persistence_succeeded)
        self.assertEqual(result.templates_registered, 2)

    def test_persistence_failure_keeps_successful_memory_gallery(self):
        gallery, workflow = self.workflow()
        workflow.start(self.form(persist=True))
        workflow.add_accepted_sample(self.embedding([1, 0]), None, "frontal")
        workflow.add_accepted_sample(self.embedding([.8, .2], index=1), None, "left")

        def fail(*args):
            raise OSError("controlled persistence failure")

        result = workflow.finish(
            persistence=fail, manifest_path=Path("unused.json"),
            archive_path=Path("unused.npz"),
        )
        self.assertFalse(result.persistence_succeeded)
        self.assertEqual(len(gallery), 1)
        self.assertEqual(len(gallery.templates()), 2)
        self.assertIn("galería en memoria", result.message)


if __name__ == "__main__":
    unittest.main()
