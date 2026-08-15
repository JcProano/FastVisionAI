import tempfile
import unittest
import uuid
from pathlib import Path

from src.core.person_database import PersonCreateRequest, PersonRepository, PersonStatus
from src.engine.gallery import FaceGallery, FaceIdentity
from src.ui.form_validation import RegistrationFormError, validate_registration_form
from src.ui.identification.database_provider import SQLiteThumbnailIdentityInfoProvider
from src.core.person_database import SQLiteIdentityDataProvider
from src.ui.main import GALLERY_SYNC_WARNING, civil_gallery_sync_warning


class _Thumbnails:
    def load(self, person_id):
        from src.ui.thumbnails import ThumbnailDTO
        return ThumbnailDTO(person_id, False, 0, 0, "jpeg", None)


class PersonDatabaseUIIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.repository = PersonRepository(Path(self.temporary.name) / "people.db")
        self.repository.initialize()

    def test_full_form_normalizes_civil_data_and_generates_uuid(self):
        form = validate_registration_form(
            "  Ana ", " Pérez  ", None, consent_confirmed=True,
            persist_locally=False, cedula="1710034065", phone="+593 99-123-4567",
            email="ANA@example.test", birth_date="2000-01-02",
        )
        uuid.UUID(form.person_id)
        self.assertEqual((form.first_name, form.last_name), ("Ana", "Pérez"))
        self.assertEqual(form.cedula, "1710034065")
        self.assertEqual(form.email, "ANA@example.test")

    def test_invalid_civil_form_is_rejected_before_enrollment(self):
        with self.assertRaises(RegistrationFormError):
            validate_registration_form(
                "Ana", "Pérez", None, consent_confirmed=True,
                persist_locally=False, cedula="0000000000",
            )

    def test_civil_gallery_mismatch_is_reported_without_automatic_merge(self):
        person_id = str(uuid.uuid4())
        self.repository.create(PersonCreateRequest(
            person_id, "1710034065", "Ana", "Pérez",
        ))
        self.repository.set_status(person_id, PersonStatus.ACTIVE)
        gallery = FaceGallery()
        other_id = str(uuid.uuid4())
        gallery.register_identity(FaceIdentity(other_id, "Biometric identity"))
        self.assertEqual(
            civil_gallery_sync_warning(self.repository, gallery), GALLERY_SYNC_WARNING,
        )
        self.assertIsNotNone(self.repository.get_by_person_id(person_id))
        self.assertEqual(gallery.list_identities()[0].person_id, other_id)

    def test_matching_active_person_and_gallery_has_no_warning(self):
        person_id = str(uuid.uuid4())
        self.repository.create(PersonCreateRequest(
            person_id, "1710034065", "Ana", "Pérez",
        ))
        self.repository.set_status(person_id, PersonStatus.ACTIVE)
        gallery = FaceGallery(); gallery.register_identity(FaceIdentity(person_id, "Ana"))
        self.assertIsNone(civil_gallery_sync_warning(self.repository, gallery))

    def test_provider_exposes_only_active_and_labels_gallery_legacy(self):
        gallery = FaceGallery()
        active_id = str(uuid.uuid4())
        pending_id = str(uuid.uuid4())
        self.repository.create(PersonCreateRequest(
            active_id, "1710034065", "Ana", "Pérez", address="Quito",
        ))
        self.repository.set_status(active_id, PersonStatus.ACTIVE)
        self.repository.create(PersonCreateRequest(
            pending_id, "0926687856", "Pending", "Person",
        ))
        legacy_id = str(uuid.uuid4())
        gallery.register_identity(FaceIdentity(legacy_id, "Legacy", {}))
        provider = SQLiteThumbnailIdentityInfoProvider(
            SQLiteIdentityDataProvider(self.repository), _Thumbnails(), gallery,
        )
        active = provider.get_person(active_id)
        self.assertEqual(active.address, "Quito")
        self.assertIsNone(provider.get_person(pending_id))
        legacy = provider.get_person(legacy_id)
        self.assertTrue(legacy.legacy_without_civil_data)
        self.assertIn("heredado", legacy.display_name)


if __name__ == "__main__":
    unittest.main()
