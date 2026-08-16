import tempfile
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.core.detection_events import DetectionEventRepository
from src.core.person_database import PersonCreateRequest, PersonRepository, PersonStatus
from src.ui.detection_history import DetectionHistoryController
from src.ui.identification import IdentityPersonDTO
from src.ui.thumbnails import ThumbnailDTO
from tests.test_detection_event_repository import record


class DetectionHistoryControllerTests(unittest.TestCase):
    def test_resolves_name_person_id_and_only_masked_cedula(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            events = DetectionEventRepository(root / "events.db"); events.initialize()
            people = PersonRepository(root / "people.db"); people.initialize()
            person_id = str(uuid.uuid4())
            people.create(PersonCreateRequest(person_id, "1710034065", "Ana", "Temporal"))
            people.set_status(person_id, PersonStatus.ACTIVE)
            events.create(record(person_id=person_id))
            controller = DetectionHistoryController(events, people)
            result = controller.list(name="ana")
            self.assertEqual(result.events[0].person_id, person_id)
            self.assertEqual(result.events[0].masked_cedula, "******4065")
            self.assertNotIn("1710034065", repr(result))

    def test_cedula_filter_detail_and_thumbnail_are_resolved_dynamically(self):
        class Provider:
            def get_person(self, person_id):
                return IdentityPersonDTO(person_id, "Ana", "Temporal", "Ana Temporal",
                                         "1710034065", phone="0999999999")
            def get_thumbnail(self, person_id):
                return ThumbnailDTO(person_id, False, 0, 0, "NONE")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            events = DetectionEventRepository(root / "events.db"); events.initialize()
            people = PersonRepository(root / "people.db"); people.initialize()
            person_id = str(uuid.uuid4())
            people.create(PersonCreateRequest(person_id, "1710034065", "Ana", "Temporal"))
            people.set_status(person_id, PersonStatus.ACTIVE)
            events.create(record(person_id=person_id, camera="Entrada principal"))
            controller = DetectionHistoryController(events, people, identity_provider=Provider())
            result = controller.list(cedula="1710034065", camera_id="Entrada principal",
                                     administrative_status="ACTIVE")
            self.assertEqual(result.total, 1)
            detail = controller.detail(result.events[0].event_id)
            self.assertEqual(detail.person.phone, "0999999999")
            self.assertFalse(detail.thumbnail.available)


if __name__ == "__main__": unittest.main()
