import tempfile
import unittest
import uuid
from pathlib import Path

from src.core.person_database import PersonCreateRequest, PersonRepository, PersonStatus
from src.ui.people.contracts import PeopleManagerState
from src.ui.people.database_controller import DatabasePeopleManagerController


class _Biometrics:
    state = PeopleManagerState.IDLE
    manifest_path = Path("unused.json")
    archive_path = Path("unused.npz")

    def details(self, person_id):
        raise KeyError(person_id)

    def begin_additional(self, person_id):
        from src.ui.people.contracts import PeopleOperationResultDTO
        return PeopleOperationResultDTO(
            PeopleManagerState.ENROLLING_MORE, True, "additional_start", "ok", person_id,
        )


class DatabasePeopleManagerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.repository = PersonRepository(Path(temporary.name) / "people.db")
        self.repository.initialize()
        self.person_id = str(uuid.uuid4())
        self.repository.create(PersonCreateRequest(
            self.person_id, "1710034065", "Ana", "Pérez", email="ana@example.test",
        ))
        self.controller = DatabasePeopleManagerController(self.repository, _Biometrics())

    def test_search_civil_edit_clear_and_cedula_is_validated(self):
        self.assertEqual(self.controller.list_people("PÉREZ").total_identities, 1)
        edited = self.controller.update_person(
            self.person_id, "Ana María", "Pérez", "1710034065", email="",
        )
        self.assertTrue(edited.success)
        record = self.repository.get_by_person_id(self.person_id)
        self.assertEqual(record.first_name, "Ana María")
        self.assertIsNone(record.email)
        changed = self.controller.update_person(
            self.person_id, "Ana", "Pérez", "0926687856",
        )
        self.assertTrue(changed.success)
        self.assertEqual(self.repository.get_by_person_id(self.person_id).cedula, "0926687856")

    def test_delete_is_blocked_and_additional_requires_active(self):
        self.assertFalse(self.controller.delete_person(self.person_id, confirmed=True).success)
        self.assertFalse(self.controller.begin_additional(self.person_id).success)
        self.repository.set_status(self.person_id, PersonStatus.ACTIVE)
        self.assertTrue(self.controller.begin_additional(self.person_id).success)


if __name__ == "__main__":
    unittest.main()
