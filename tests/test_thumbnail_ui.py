import inspect
import unittest
from unittest.mock import patch

from src.ui.people.tk_window import PeopleManagerWindow
from src.ui.thumbnails.contracts import ThumbnailDTO
from src.ui.tk_app import LocalFaceTkApp


class Label:
    def __init__(self): self.values = {}
    def configure(self, **values): self.values.update(values)


class ThumbnailUITests(unittest.TestCase):
    def test_dashboard_loads_only_when_candidate_changes(self):
        app = object.__new__(LocalFaceTkApp)
        app._thumbnail_person_id = None
        app._thumbnail_photo = None
        app.candidate_thumbnail = Label()
        calls = []
        app._get_thumbnail = lambda person_id: (
            calls.append(person_id) or ThumbnailDTO(person_id, False, 0, 0, "jpeg")
        )
        app._refresh_candidate_thumbnail("person_a")
        app._refresh_candidate_thumbnail("person_a")
        app._refresh_candidate_thumbnail("person_b")
        self.assertEqual(calls, ["person_a", "person_b"])

    def test_old_identity_uses_placeholder_and_people_actions_are_explicit(self):
        app = object.__new__(LocalFaceTkApp)
        app._thumbnail_person_id = None; app._thumbnail_photo = object()
        app.candidate_thumbnail = Label(); app._get_thumbnail = None
        app._refresh_candidate_thumbnail("person_old")
        self.assertEqual(app.candidate_thumbnail.values["text"], "Sin foto registrada")
        source = inspect.getsource(PeopleManagerWindow)
        self.assertIn("Actualizar foto", source)
        self.assertIn("Eliminar foto", source)
        self.assertIn("askyesno", source)
        self.assertNotIn("cv2", source)


if __name__ == "__main__":
    unittest.main()
