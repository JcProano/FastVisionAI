import inspect
import json
import unittest
from unittest.mock import Mock, patch
from datetime import datetime, timezone
from pathlib import Path

from src.ui.identification.contracts import IdentificationPopupDTO, IdentificationPopupType
from src.ui.identification.tk_popup import IdentificationPopupWindow
from src.ui.tk_app import LocalFaceTkApp


class IdentificationPopupTests(unittest.TestCase):
    class FakeRoot:
        def __init__(self): self.callbacks = {}; self.next_id = 0; self.cancelled = []
        def after(self, _delay, callback):
            self.next_id += 1; self.callbacks[self.next_id] = callback; return self.next_id
        def after_cancel(self, identifier):
            self.cancelled.append(identifier); self.callbacks.pop(identifier, None)
        def run(self, identifier): self.callbacks.pop(identifier)()

    class FakeWidget:
        def __init__(self): self.values = {}; self.exists = True
        def configure(self, **values): self.values.update(values)
        def winfo_exists(self): return self.exists
        def destroy(self): self.exists = False
        def lift(self): self.values["lifted"] = True

    def popup(self):
        clock = [0.0]; root = self.FakeRoot(); closed = []; registered = []
        popup = IdentificationPopupWindow.__new__(IdentificationPopupWindow)
        popup.root = root; popup.provider = None
        popup._on_view_person = lambda _person_id: None
        popup._on_register = lambda: registered.append(True)
        popup._unknown_timeout_seconds = 60.0
        popup._on_unknown_closed = lambda: closed.append(True)
        popup._on_dismissed = None
        popup._monotonic = lambda: clock[0]
        popup.window = self.FakeWidget(); popup._photo = None; popup._person_id = None
        popup._popup_type = None; popup._timer_id = None; popup._unknown_deadline = None
        popup._registered_deadline = None
        popup.title = self.FakeWidget(); popup.thumbnail = self.FakeWidget()
        popup.right_title = self.FakeWidget()
        popup.details = self.FakeWidget(); popup.countdown = self.FakeWidget()
        popup.primary = self.FakeWidget(); popup.secondary = self.FakeWidget()
        return popup, clock, root, closed, registered

    @staticmethod
    def registered(*, thumbnail=True):
        return IdentificationPopupDTO(
            IdentificationPopupType.REGISTERED_CANDIDATE, "person-safe",
            "Temporary Person", "******1234", .924, "NOT_EVALUATED", thumbnail,
            "safe", datetime(2026, 8, 14, 12, 0, tzinfo=timezone.utc),
            phone="0990000000", email="temporary@example.test", civil_status="ACTIVE",
            registered_at=datetime(2026, 8, 1, tzinfo=timezone.utc),
        )

    @staticmethod
    def unknown():
        return IdentificationPopupDTO(
            IdentificationPopupType.UNREGISTERED, None, None, None, None,
            "NO_GALLERY", False, "Sin candidato", datetime.now(timezone.utc),
        )

    def test_unknown_timeout_configuration_and_monotonic_countdown(self):
        config = json.loads(Path("config/local_face_validation.dev.json").read_text())
        self.assertEqual(config["identification_popup"]["unknown_popup_timeout_seconds"], 60.0)
        popup, clock, root, closed, registered = self.popup(); popup._render(self.unknown())
        self.assertEqual(popup.countdown.values["text"], "Tiempo restante para decidir: 01:00")
        clock[0] = 1.0; root.run(popup._timer_id)
        self.assertEqual(popup.countdown.values["text"], "Tiempo restante para decidir: 00:59")
        clock[0] = 60.0; root.run(popup._timer_id)
        self.assertEqual(popup.countdown.values["text"], "Tiempo restante para decidir: 00:00")
        self.assertFalse(popup.active); self.assertEqual(closed, [True])
        self.assertFalse(root.callbacks)
        self.assertFalse(registered)  # expiration never starts enrollment/reservation

    def test_register_ignore_and_application_close_cancel_timer(self):
        for action in ("register", "ignore", "close"):
            with self.subTest(action=action):
                popup, _, root, closed, registered = self.popup(); popup._render(self.unknown())
                timer = popup._timer_id
                getattr(popup, "_register" if action == "register" else
                        "dismiss" if action == "ignore" else "close")()
                self.assertIn(timer, root.cancelled); self.assertFalse(root.callbacks)
                self.assertEqual(closed, [True])
                self.assertEqual(bool(registered), action == "register")

    def test_dismiss_callback_runs_after_cleanup_and_failure_is_safe(self):
        popup, _, root, _, _ = self.popup(); notices = []
        popup._on_dismissed = lambda popup_type, reason: notices.append(
            (popup_type, reason, popup.active, bool(root.callbacks))
        )
        popup._render(self.unknown()); popup.dismiss("programmatic")
        self.assertEqual(notices, [("UNREGISTERED", "programmatic", False, False)])

        popup, _, _, _, _ = self.popup()
        popup._on_dismissed = lambda *_args: (_ for _ in ()).throw(RuntimeError())
        popup._render(self.unknown()); popup.dismiss("user")
        self.assertFalse(popup.active)

    def test_popup_text_actions_singleton_and_thumbnail_placeholder(self):
        source = inspect.getsource(IdentificationPopupWindow)
        for expected in (
            "✔ IDENTIFICACIÓN EXITOSA", "PERSONA IDENTIFICADA",
            "PERSONA NO REGISTRADA EN LA GALERÍA LOCAL",
            "Estado: IDENTIFICADO", "Ver detalles", "Registrar persona",
            "Sin fotografía registrada",
            "winfo_exists", "lift",
        ):
            self.assertIn(expected, source)

    def test_registered_popup_with_photo_and_safe_information(self):
        popup, _, _, _, _ = self.popup()
        popup.provider = Mock()
        popup.provider.get_thumbnail.return_value = Mock()
        with patch("src.ui.identification.tk_popup.thumbnail_to_ppm", return_value=b"ppm"), \
             patch("src.ui.identification.tk_popup.tk.PhotoImage", return_value="photo"):
            popup._render(self.registered())
        self.assertEqual(popup.thumbnail.values["image"], "photo")
        self.assertEqual(popup.title.values["text"], "✔ IDENTIFICACIÓN EXITOSA")
        self.assertIn("Temporary Person", popup.details.values["text"])
        self.assertIn("Score de reconocimiento: 92.4 %", popup.details.values["text"])
        self.assertIn("Estado: IDENTIFICADO", popup.details.values["text"])
        self.assertNotIn("person-safe", popup.details.values["text"])

    def test_registered_popup_without_photo_uses_placeholder(self):
        popup, _, _, _, _ = self.popup()
        popup._render(self.registered(thumbnail=False))
        self.assertIn("Sin fotografía registrada", popup.thumbnail.values["text"])

    def test_missing_registered_data_is_explicitly_unavailable(self):
        popup, _, _, _, _ = self.popup()
        dto = IdentificationPopupDTO(
            IdentificationPopupType.REGISTERED_CANDIDATE, "person-safe", None,
            None, None, "NOT_EVALUATED", False, "safe",
            datetime.now(timezone.utc),
        )
        popup._render(dto)
        self.assertGreaterEqual(popup.details.values["text"].count("No disponible"), 8)

    def test_singleton_registered_popup_updates_only_when_person_changes(self):
        popup, _, _, _, _ = self.popup()
        first = self.registered(thumbnail=False)
        popup._popup_type = IdentificationPopupType.REGISTERED_CANDIDATE
        popup._person_id = first.person_id
        popup._render = Mock()
        popup.show(first)
        popup._render.assert_not_called()
        changed = IdentificationPopupDTO(
            IdentificationPopupType.REGISTERED_CANDIDATE, "person-other",
            "Other Person", "******5678", .8, "NOT_EVALUATED", False,
            "safe", datetime.now(timezone.utc),
        )
        popup.show(changed)
        popup._render.assert_called_once_with(changed)

    def test_registered_countdown_manual_and_automatic_close(self):
        popup, clock, root, _, _ = self.popup()
        popup._render(self.registered(thumbnail=False))
        self.assertEqual(popup.secondary.values["text"], "Cerrar (5)")
        clock[0] = 1; root.run(popup._timer_id)
        self.assertEqual(popup.secondary.values["text"], "Cerrar (4)")
        clock[0] = 5; root.run(popup._timer_id)
        self.assertEqual(popup.secondary.values["text"], "Cerrar (0)")
        self.assertFalse(popup.active); self.assertFalse(root.callbacks)

        popup, _, root, _, _ = self.popup(); popup._render(self.registered(thumbnail=False))
        timer = popup._timer_id; popup.dismiss("user")
        self.assertIn(timer, root.cancelled); self.assertFalse(root.callbacks)

    def test_enter_escape_x_and_modal_wiring(self):
        source = inspect.getsource(IdentificationPopupWindow._build)
        for expected in (
            'bind("<Return>"', 'bind("<Escape>"',
            'protocol("WM_DELETE_WINDOW", self.dismiss)', "grab_set()",
            "update_idletasks()", "focus_force()",
        ):
            self.assertIn(expected, source)

    def test_callbacks_and_close_are_wired_without_duplicate_form(self):
        popup_source = inspect.getsource(IdentificationPopupWindow)
        app_source = inspect.getsource(LocalFaceTkApp)
        self.assertIn("self._on_view_person", popup_source)
        self.assertIn("self._on_register", popup_source)
        self.assertIn("self._identification_popup.close()", app_source)
        self.assertIn("self._dismiss_identification_popup(", app_source)
        self.assertIn("self.open_form", app_source)
        self.assertIn("UIState.MULTIPLE_FACES", app_source)
        self.assertIn("UIState.NO_FACE", app_source)
        self.assertIn("self._dismiss_identification_popup(", inspect.getsource(LocalFaceTkApp.show_progress))
        self.assertIn("IdentificationPopupType.REGISTERED_CANDIDATE", app_source)

    def test_forbidden_access_language_is_absent(self):
        source = inspect.getsource(IdentificationPopupWindow).casefold()
        for forbidden in (
            "identidad confirmada", "persona identificada biométricamente",
            "acceso autorizado", "acceso denegado",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__": unittest.main()
