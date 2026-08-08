import inspect
import unittest

from src.ui.people.tk_window import PeopleManagerWindow
from src.ui.person_profile.tk_window import PersonProfileWindow
from src.ui import main as ui_main


class PersonProfileWindowTests(unittest.TestCase):
    def test_window_has_safe_states_actions_and_no_biometric_language(self):
        source = inspect.getsource(PersonProfileWindow)
        for text in ("Sin foto registrada", "Editar datos", "Agregar muestras", "N/D"):
            self.assertIn(text, source)
        for forbidden in ("embedding", "weights_sha256", "FaceTemplate"):
            self.assertNotIn(forbidden, source)

    def test_people_manager_exposes_view_profile_callback(self):
        source = inspect.getsource(PeopleManagerWindow)
        self.assertIn("Ver ficha", source)
        self.assertIn("_on_view_profile", source)

    def test_composition_root_uses_person_id_singletons_and_popup_profile_callback(self):
        source = inspect.getsource(ui_main.main)
        self.assertIn("profile_windows.get(person_id)", source)
        self.assertIn("current.focus()", source)
        self.assertIn("on_view_person=open_profile", source)
        self.assertIn("on_view_profile=open_profile", source)


if __name__ == "__main__":
    unittest.main()
