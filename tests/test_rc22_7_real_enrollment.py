from __future__ import annotations

import json
import tempfile
import unittest
import uuid
from dataclasses import replace
from pathlib import Path

import numpy as np

from src.core.person_database import PersonCreateRequest, PersonRepository, PersonStatus
from src.engine.enrollment import EnrollmentPolicy, EnrollmentService
from src.engine.gallery import FaceGallery
from src.engine.gallery.persistence import GalleryPersistence
from src.ui.contracts import RegistrationFormData
from src.ui.enrollment_workflow import LocalEnrollmentWorkflow
from src.ui.live_session import _verify_enrollment_commit
from src.ui.main import build_persistence
from src.ui.people.controller import PeopleManagerController
from src.ui.people.database_controller import DatabasePeopleManagerController
from src.ui.person_enrollment import PersonEnrollmentCoordinator
from tests.test_face_gallery import GalleryTestCase


class RC227RealEnrollmentTests(GalleryTestCase):
    def samples(self):
        return tuple(
            self.embedding([1.0, value / 100.0]) for value in range(5)
        )

    def test_first_civil_person_five_templates_persist_and_reload(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = PersonRepository(root / "people.db")
            repository.initialize()
            gallery = FaceGallery()
            workflow = LocalEnrollmentWorkflow(
                gallery, EnrollmentService(gallery, EnrollmentPolicy(5, 5)), 5,
            )
            coordinator = PersonEnrollmentCoordinator(
                repository, gallery, workflow,
            )
            person_id = str(uuid.uuid4())
            form = RegistrationFormData(
                "First", "Person", "First Person", person_id, None,
                True, True, "1710034065",
            )

            coordinator.begin(form)
            for index, embedding in enumerate(self.samples(), 1):
                workflow.add_accepted_sample(embedding, None, f"sample {index}")
            result = coordinator.commit()
            callback, manifest, archive = build_persistence(
                {"persistence": {"directory": "gallery"}}, root,
            )
            callback(gallery, manifest, archive)
            result = replace(
                result, persistence_requested=True, persistence_succeeded=True,
            )
            _verify_enrollment_commit(result, gallery, manifest, archive, 5)

            reloaded = FaceGallery()
            GalleryPersistence(enabled=True).import_into(reloaded, manifest, archive)
            self.assertEqual(repository.count(), 1)
            self.assertIs(repository.get_by_person_id(person_id).status, PersonStatus.ACTIVE)
            self.assertEqual([item.person_id for item in reloaded.list_identities()], [person_id])
            self.assertEqual(len(reloaded.templates(person_id)), 5)
            manifest_value = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(manifest_value["identities"][0]["person_id"], person_id)
            with np.load(archive, allow_pickle=False) as stored:
                self.assertEqual(len(stored.files), 5)

    def test_update_face_recovers_active_civil_person_missing_from_gallery(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repository = PersonRepository(root / "people.db")
            repository.initialize()
            person_id = str(uuid.uuid4())
            repository.create(PersonCreateRequest(
                person_id, "1710034065", "Civil", "Only",
            ))
            repository.set_status(person_id, PersonStatus.ACTIVE)
            gallery = FaceGallery()
            biometrics = PeopleManagerController(
                gallery, EnrollmentService(gallery, EnrollmentPolicy(1, 5)),
                GalleryPersistence(enabled=True), root / "gallery.json", root / "gallery.npz",
            )
            people = DatabasePeopleManagerController(repository, biometrics)

            started = people.begin_replacement(person_id)
            completed = people.complete_additional(
                person_id, tuple((item, None) for item in self.samples()),
            )

            self.assertTrue(started.success)
            self.assertTrue(completed.success)
            self.assertEqual(repository.count(), 1)
            self.assertEqual(len(gallery.templates(person_id)), 5)
            reloaded = FaceGallery()
            GalleryPersistence(enabled=True).import_into(
                reloaded, root / "gallery.json", root / "gallery.npz",
            )
            self.assertEqual(len(reloaded.templates(person_id)), 5)


if __name__ == "__main__":
    unittest.main()
