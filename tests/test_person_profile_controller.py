import tempfile
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.core.person_database import PersonCreateRequest, PersonRepository, PersonStatus
from src.engine.alignment import AlignmentQuality
from src.engine.enrollment import EnrollmentPolicy, EnrollmentService
from src.engine.face_quality.contracts import FaceQualityScore, QualityBand
from src.engine.gallery import FaceGallery, FaceIdentity, FaceTemplate
from src.engine.gallery.persistence import GalleryPersistence
from src.ui.people.controller import PeopleManagerController, record_template_quality_scores
from src.ui.people.database_controller import DatabasePeopleManagerController
from src.ui.person_profile import PersonProfileController, PersonProfileStatus
from src.ui.thumbnails import ThumbnailManager
from tests.test_face_gallery import GalleryTestCase
from tests.test_thumbnail_manager import image_bytes


class PersonProfileControllerTests(GalleryTestCase):
    def setUp(self):
        super().setUp()
        self.temporary = tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repository = PersonRepository(self.root / "people.db"); self.repository.initialize()
        self.gallery = FaceGallery()
        self.biometrics = PeopleManagerController(
            self.gallery, EnrollmentService(self.gallery, EnrollmentPolicy(1, 5)),
            GalleryPersistence(enabled=True), self.root / "gallery.json", self.root / "gallery.npz",
        )
        self.administration = DatabasePeopleManagerController(self.repository, self.biometrics)
        self.thumbnails = ThumbnailManager(self.root, Path("thumbnails"))
        self.controller = PersonProfileController(
            self.repository, self.administration, self.biometrics, self.thumbnails,
        )
        self._cedulas = iter(("1710034065", "0926687856"))

    def add_civil(self, status=PersonStatus.ACTIVE):
        person_id = str(uuid.uuid4())
        self.repository.create(PersonCreateRequest(
            person_id, next(self._cedulas), "Ana", "Pérez", address="Quito",
        ))
        if status is not PersonStatus.PENDING_BIOMETRIC:
            self.repository.set_status(person_id, status)
        return person_id

    def add_identity(self, person_id):
        self.gallery.register_identity(FaceIdentity(person_id, "Ana Pérez", {}))

    def test_active_lookup_by_cedula_thumbnail_and_statistics(self):
        person_id = self.add_civil(); self.add_identity(person_id)
        first = datetime(2025, 1, 1, tzinfo=timezone.utc)
        second = first + timedelta(days=2)
        for index, created in enumerate((first, second)):
            vector = self.embedding([1, index + 1, 0]).embedding
            self.gallery.add_template(person_id, FaceTemplate(
                self.gallery.list_identities()[0], vector, 3, "model", "1", "sha",
                created, AlignmentQuality.VALID,
            ))
        score = FaceQualityScore(
            88, 80, 80, 80, 80, 80, 80, 80, 80, 80,
            QualityBand.GOOD, "quality-dev", "1", (), "run", 0,
        )
        record_template_quality_scores(self.gallery, person_id, ((0, score),))
        self.thumbnails.save(person_id, image_bytes())
        profile = self.controller.get_by_cedula("1710034065")
        self.assertEqual(profile.administrative_status, PersonProfileStatus.ACTIVE)
        self.assertEqual((profile.template_count, profile.scored_template_count), (2, 1))
        self.assertEqual(profile.average_quality_score, 88)
        self.assertEqual((profile.first_template_at, profile.last_template_at), (first, second))
        self.assertTrue(profile.thumbnail_available)

    def test_pending_disabled_legacy_not_found_and_no_scores(self):
        pending = self.add_civil(PersonStatus.PENDING_BIOMETRIC)
        disabled = self.add_civil(PersonStatus.DISABLED)
        legacy = str(uuid.uuid4()); self.add_identity(legacy)
        self.assertEqual(self.controller.get_by_person_id(pending).administrative_status,
                         PersonProfileStatus.PENDING_BIOMETRIC)
        self.assertEqual(self.controller.get_by_person_id(disabled).administrative_status,
                         PersonProfileStatus.DISABLED)
        legacy_profile = self.controller.get_by_person_id(legacy)
        self.assertTrue(legacy_profile.legacy_biometric_record)
        self.assertEqual(legacy_profile.administrative_status,
                         PersonProfileStatus.LEGACY_BIOMETRIC_ONLY)
        missing = self.controller.get_by_person_id(str(uuid.uuid4()))
        self.assertEqual(missing.administrative_status, PersonProfileStatus.NOT_FOUND)
        self.assertIsNone(missing.average_quality_score)

    def test_edit_refreshes_real_source_and_additional_is_active_only(self):
        active = self.add_civil(); self.add_identity(active)
        updated = self.controller.update_person(
            active, first_name="Ana María", last_name="Pérez", address="Cuenca",
        )
        self.assertTrue(updated.success)
        self.assertEqual(updated.profile.first_name, "Ana María")
        self.assertEqual(updated.profile.cedula, "1710034065")
        self.assertTrue(self.controller.begin_additional(active).success)
        pending = self.add_civil(PersonStatus.PENDING_BIOMETRIC)
        self.assertFalse(self.controller.begin_additional(pending).success)


if __name__ == "__main__":
    unittest.main()
