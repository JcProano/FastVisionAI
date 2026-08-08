import tempfile
import unittest
import uuid
from pathlib import Path

from src.core.person_database import (
    DuplicateCedulaError, DuplicatePersonIdError, PersonCreateRequest,
    PersonRepository, PersonSearchQuery, PersonStatus, PersonUpdateRequest,
    SQLiteIdentityDataProvider,
)


def request(cedula="1710034065", person_id=None, first="Temporary", last="Person"):
    return PersonCreateRequest(
        person_id or str(uuid.uuid4()), cedula, first, last,
        address="Quito", phone="0991234567", email=f"{first.lower()}@example.com",
        birth_date="2000-01-01", sex="unspecified", notes="development fixture",
    )


class PersonRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.repository = PersonRepository(Path(self.temporary.name) / "nested" / "people.db")
        self.repository.initialize()

    def tearDown(self): self.temporary.cleanup()

    def test_create_get_count_and_provider(self):
        created = self.repository.create(request())
        self.assertEqual(created.status, PersonStatus.PENDING_BIOMETRIC)
        self.assertEqual(self.repository.count(), 1)
        self.assertEqual(self.repository.get_by_person_id(created.person_id), created)
        self.assertEqual(self.repository.get_by_cedula(created.cedula), created)
        provider = SQLiteIdentityDataProvider(self.repository)
        self.assertEqual(provider.get_by_person_id(created.person_id), created)

    def test_duplicate_cedula_person_id_and_rollback(self):
        original = self.repository.create(request())
        with self.assertRaises(DuplicateCedulaError):
            self.repository.create(request(cedula=original.cedula))
        with self.assertRaises(DuplicatePersonIdError):
            self.repository.create(request("0926687856", person_id=original.person_id))
        self.assertEqual(self.repository.count(), 1)
        self.assertEqual(self.repository.get_by_person_id(original.person_id), original)

    def test_update_clear_status_and_delete(self):
        created = self.repository.create(request())
        updated = self.repository.update(PersonUpdateRequest(
            created.person_id, first_name="Updated", phone="+593 98 765 4321",
            clear_fields=frozenset({"notes"}),
        ))
        self.assertEqual(updated.first_name, "Updated")
        self.assertEqual(updated.phone, "+593987654321")
        self.assertIsNone(updated.notes)
        active = self.repository.set_status(created.person_id, PersonStatus.ACTIVE)
        self.assertEqual(active.status, PersonStatus.ACTIVE)
        self.assertTrue(self.repository.delete(created.person_id))
        self.assertFalse(self.repository.delete(created.person_id))

    def test_list_search_exists_and_stats(self):
        first = self.repository.create(request(first="Alpha", last="Zulu"))
        second = self.repository.create(request("0926687856", first="Beta", last="Andes"))
        second = self.repository.set_status(second.person_id, PersonStatus.ACTIVE)
        self.assertEqual([item.person_id for item in self.repository.list()],
                         [second.person_id, first.person_id])
        self.assertEqual(self.repository.search(PersonSearchQuery(first_name="alp"))[0], first)
        self.assertEqual(self.repository.search(PersonSearchQuery(email="BETA@EXAMPLE"))[0], second)
        self.assertTrue(self.repository.exists_cedula("1710034065"))
        stats = self.repository.stats()
        self.assertEqual((stats.total, stats.pending_biometric, stats.active), (2, 1, 1))


if __name__ == "__main__": unittest.main()
