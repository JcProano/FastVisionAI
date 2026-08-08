import tempfile
import unittest
import uuid
from pathlib import Path

from src.core.person_database import PersonCreateRequest, PersonRepository, PersonStatus
from src.engine.gallery import FaceGallery, FaceIdentity
from src.ui.form_validation import RegistrationFormError, validate_registration_form
from src.ui.identification.database_provider import SQLiteThumbnailIdentityInfoProvider
from src.core.person_database import SQLiteIdentityDataProvider


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
