"""RC22.10 regression coverage for the registered-people face action."""

from __future__ import annotations

import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from src.ui.people.tk_window import PeopleManagerWindow


class RC2210PeopleFaceActionTests(unittest.TestCase):
    def _window(self, *, status: str, templates: int = 0):
        window = PeopleManagerWindow.__new__(PeopleManagerWindow)
        person = SimpleNamespace(
            person_id="same-person-id", display_name="Persona Civil",
            civil_status=status, template_count=templates,
        )
        window.selected = Mock(return_value=person)
        window._on_replace_face = Mock(return_value=True)
        window._on_register_face = Mock(return_value=True)
        window._on_reactivate_person = Mock(return_value=True)
        window._camera_available = Mock(return_value=True)
        window.status = Mock()
        window.refresh = Mock()
        window.window = object()
        return window

    @patch("src.ui.people.tk_window.messagebox")
    def test_disabled_offers_reactivation_and_does_not_start_enrollment(self, dialogs):
        dialogs.askyesno.return_value = True
        window = self._window(status="DISABLED")

        window.replace_face()

        window._on_reactivate_person.assert_called_once_with("same-person-id")
        window._on_replace_face.assert_not_called()
        window.refresh.assert_called_once()
        self.assertIn("PERSONA DESHABILITADA", dialogs.askyesno.call_args.args[0])

    @patch("src.ui.people.tk_window.messagebox")
    def test_active_without_templates_registers_without_replacement_language(self, dialogs):
        dialogs.askyesno.return_value = True
        window = self._window(status="ACTIVE", templates=0)

        window.replace_face()

        title, prompt = dialogs.askyesno.call_args.args[:2]
        self.assertEqual(title, "REGISTRAR ROSTRO")
        self.assertIn("no tiene rostro registrado", prompt)
        self.assertNotIn("Reemplazar", prompt)
        window._on_register_face.assert_called_once_with("same-person-id")
        window._on_replace_face.assert_not_called()

    @patch("src.ui.people.tk_window.messagebox")
    def test_active_with_templates_confirms_replacement(self, dialogs):
        dialogs.askyesno.return_value = True
        window = self._window(status="ACTIVE", templates=5)

        window.replace_face()

        title, prompt = dialogs.askyesno.call_args.args[:2]
        self.assertEqual(title, "ACTUALIZAR ROSTRO")
        self.assertIn("Reemplazar los templates faciales existentes", prompt)
        window._on_replace_face.assert_called_once_with("same-person-id")

    @patch("src.ui.people.tk_window.messagebox")
    def test_missing_camera_does_not_start_or_change_civil_status(self, dialogs):
        window = self._window(status="ACTIVE", templates=0)
        window._camera_available.return_value = False

        window.replace_face()

        window._on_replace_face.assert_not_called()
        window._on_reactivate_person.assert_not_called()
        dialogs.askyesno.assert_not_called()
        window.status.configure.assert_called_with(
            text="Seleccione una cámara antes de iniciar el registro facial."
        )

    def test_real_callback_and_safe_logging_are_wired(self):
        window_source = inspect.getsource(PeopleManagerWindow.replace_face)
        self.assertIn("self._on_register_face if missing_face", window_source)
        self.assertIn("callback(person.person_id)", window_source)
        self.assertIn("No se pudo iniciar el registro facial.", window_source)


if __name__ == "__main__":
    unittest.main()
