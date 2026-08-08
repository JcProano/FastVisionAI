import inspect
import unittest

from src.ui.identification.tk_popup import IdentificationPopupWindow
from src.ui.tk_app import LocalFaceTkApp


class IdentificationPopupTests(unittest.TestCase):
    def test_popup_text_actions_singleton_and_thumbnail_placeholder(self):
        source = inspect.getsource(IdentificationPopupWindow)
        for expected in (
            "PERSONA REGISTRADA EN LA GALERÍA LOCAL",
            "PERSONA NO REGISTRADA EN LA GALERÍA LOCAL",
            "Candidato experimental registrado", "NOT_EVALUATED",
            "Ver persona", "Registrar persona", "Sin foto registrada",
            "winfo_exists", "lift",
        ):
            self.assertIn(expected, source)

    def test_callbacks_and_close_are_wired_without_duplicate_form(self):
        popup_source = inspect.getsource(IdentificationPopupWindow)
        app_source = inspect.getsource(LocalFaceTkApp)
        self.assertIn("self._on_view_person", popup_source)
        self.assertIn("self._on_register", popup_source)
        self.assertIn("self._identification_popup.close()", app_source)
        self.assertIn("self._identification_popup.dismiss()", app_source)
        self.assertIn("self.open_form", app_source)
        self.assertIn("UIState.MULTIPLE_FACES", app_source)
        self.assertIn("UIState.NO_FACE", app_source)

    def test_forbidden_automatic_identity_language_is_absent(self):
        source = inspect.getsource(IdentificationPopupWindow).casefold()
        for forbidden in (
            "identidad confirmada", "persona identificada biométricamente",
            "acceso autorizado", "acceso denegado", "reconocido",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__": unittest.main()
