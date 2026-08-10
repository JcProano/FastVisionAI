import dataclasses
import unittest
import uuid
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from src.core.person_database import PersonCreateRequest, PersonRepository, PersonStatus
from src.ui.people.contracts import PeopleManagerState, PeopleSearchFiltersDTO
from src.ui.people.database_controller import DatabasePeopleManagerController
from src.ui.people.search_controller import AdvancedPeopleSearchController, PeopleSearchPolicy


class Biometrics:
    state = PeopleManagerState.IDLE
    manifest_path = Path("unused.json"); archive_path = Path("unused.npz")
    def details(self, _person_id): raise KeyError()


class Thumbnails:
    def exists(self, person_id): return person_id.endswith("1")


class PeopleSearchControllerTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.repository = PersonRepository(Path(temporary.name) / "people.db")
        self.repository.initialize()
        values = (
            ("00000000-0000-0000-0000-000000000001", "1710034065", "Juan", "Pérez", "0991111111", "juan@example.test"),
            ("00000000-0000-0000-0000-000000000002", "0926687856", "ANA", "Andes", "0982222222", "ana@example.test"),
            ("00000000-0000-0000-0000-000000000003", "0100000009", "Luis", "Pérez", "0973333333", "luis@example.test"),
        )
        for person_id, cedula, first, last, phone, email in values:
            self.repository.create(PersonCreateRequest(
                person_id, cedula, first, last, phone=phone, email=email,
            ))
        self.repository.set_status(values[0][0], PersonStatus.ACTIVE)
        self.repository.set_status(values[1][0], PersonStatus.DISABLED)
        self.database = DatabasePeopleManagerController(self.repository, Biometrics())
        self.controller = AdvancedPeopleSearchController(
            self.database, Thumbnails(), PeopleSearchPolicy(
                default_page_size=25, allowed_page_sizes=(1, 2, 25, 50, 100),
            ),
        )

    def search(self, **values):
        return self.controller.search(PeopleSearchFiltersDTO(limit=25, **values))

    def test_empty_free_text_terms_spaces_and_case_insensitive(self):
        self.assertEqual(self.search().total, 3)
        self.assertEqual(self.search(text="juan").people[0].first_name, "Juan")
        result = self.search(text="  JuAn    pérez ")
        self.assertEqual([item.first_name for item in result.people], ["Juan"])
        self.assertEqual({item.first_name for item in self.search(text="PÉREZ").people},
                         {"Juan", "Luis"})

    def test_specific_cedula_phone_email_status_and_masking(self):
        self.assertEqual(self.search(cedula="1710034065").people[0].masked_cedula,
                         "******4065")
        self.assertEqual(self.search(phone="098222").people[0].first_name, "ANA")
        self.assertEqual(self.search(email="LUIS@EXAMPLE").people[0].first_name, "Luis")
        for status, name in (("ACTIVE", "Juan"), ("DISABLED", "ANA"),
                             ("PENDING_BIOMETRIC", "Luis")):
            self.assertEqual(self.search(administrative_status=status).people[0].first_name, name)

    def test_created_range_is_inclusive_exclusive(self):
        record = self.repository.get_by_person_id("00000000-0000-0000-0000-000000000001")
        self.assertEqual(self.repository.count_advanced(created_from=record.created_at), 3)
        self.assertEqual(self.repository.count_advanced(created_to=record.created_at), 0)
        today = record.created_at.astimezone(self.controller.timezone).date()
        self.assertEqual(self.search(created_from=today, created_to=today).total, 3)

    def test_pages_total_order_and_stable_tiebreak(self):
        filters = PeopleSearchFiltersDTO(limit=2, sort_by="first_name", sort_direction="ASC")
        first = self.controller.paginate(filters, 1); second = self.controller.paginate(filters, 2)
        self.assertEqual((first.first_item, first.last_item, first.total), (1, 2, 3))
        self.assertTrue(first.has_next); self.assertEqual(second.first_item, 3)
        ascending = self.repository.advanced_search(limit=25, sort_by="status", sort_direction="ASC")
        descending = self.repository.advanced_search(limit=25, sort_by="status", sort_direction="DESC")
        self.assertNotEqual([r.person_id for r in ascending], [r.person_id for r in descending])
        pending = self.repository.advanced_search(
            status=PersonStatus.PENDING_BIOMETRIC, limit=25, sort_by="status",
        )
        self.assertEqual([r.person_id for r in pending], sorted(r.person_id for r in pending))

    def test_invalid_sort_direction_pagination_and_policy(self):
        for arguments in ({"sort_by": "cedula"}, {"sort_direction": "SIDEWAYS"},
                          {"limit": 0}, {"offset": -1}):
            with self.assertRaises(ValueError): self.repository.advanced_search(**arguments)
        with self.assertRaises(ValueError):
            self.controller.search(PeopleSearchFiltersDTO(limit=3))
        with self.assertRaises(ValueError):
            PeopleSearchPolicy(default_page_size=30, allowed_page_sizes=(25, 50))

    def test_resolve_thumbnail_indicator_and_safe_dto(self):
        result = self.controller.resolve_by_cedula("1710034065")
        self.assertEqual(result.masked_cedula, "******4065"); self.assertTrue(result.thumbnail_available)
        self.assertEqual(self.controller.resolve_by_person_id(result.person_id), result)
        forbidden = {"cedula", "embedding", "template", "image", "thumbnail_bytes",
                     "address", "notes", "model"}
        self.assertFalse({field.name for field in dataclasses.fields(result)} & forbidden)

    def test_status_transitions_confirmation_pending_and_immutability(self):
        active = "00000000-0000-0000-0000-000000000001"
        cancelled = self.controller.set_status(active, PersonStatus.DISABLED, False)
        self.assertFalse(cancelled.success)
        self.assertEqual(self.repository.get_by_person_id(active).status, PersonStatus.ACTIVE)
        self.assertTrue(self.controller.set_status(active, PersonStatus.DISABLED, True).success)
        self.assertTrue(self.controller.set_status(active, PersonStatus.ACTIVE, True).success)
        pending = "00000000-0000-0000-0000-000000000003"
        self.assertFalse(self.controller.set_status(pending, PersonStatus.ACTIVE, True).success)
        record = self.repository.get_by_person_id(active)
        self.assertEqual((record.person_id, record.cedula), (active, "1710034065"))

    def test_repository_failure_is_recoverable(self):
        original = self.repository.advanced_search
        self.repository.advanced_search = lambda **_kwargs: (_ for _ in ()).throw(OSError())
        try:
            result = self.search(); self.assertFalse(result.success)
            self.assertEqual(result.message, "No se pudo consultar personas.")
        finally: self.repository.advanced_search = original


if __name__ == "__main__": unittest.main()
