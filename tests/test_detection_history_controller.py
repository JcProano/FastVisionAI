import tempfile
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.core.detection_events import DetectionEventRepository
from src.core.person_database import PersonCreateRequest, PersonRepository, PersonStatus
from src.ui.detection_history import DetectionHistoryController
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


if __name__ == "__main__": unittest.main()
