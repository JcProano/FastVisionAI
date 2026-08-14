from __future__ import annotations

import inspect
import unittest

from src.ui.contracts import RuntimeStatusDTO
from src.ui.tk_app import LocalFaceTkApp
from src.ui.camera_selection_window import CameraSelectionWindow
from src.ui import main as ui_main


class Widget:
    def __init__(self): self.values = {}
    def configure(self, **values): self.values.update(values)


class CameraDashboardTests(unittest.TestCase):
    def app(self):
        app = LocalFaceTkApp.__new__(LocalFaceTkApp)
        for name in ("runtime_status", "header_state", "camera_button", "camera_status",
                     "camera_search_button", "camera_change_button", "camera_retry_button"):
            setattr(app, name, Widget())
        return app

    def test_dashboard_without_camera_shows_disconnected_actions(self):
        app = self.app()
        app.show_runtime_status(RuntimeStatusDTO(
            "disconnected", "initialized", "loaded", "loaded", True,
            "DroidCam / OBS", "DroidCam-OBS",
        ))
        self.assertIn("Desconectada", app.camera_status.values["text"])
        self.assertEqual(app.camera_retry_button.values["state"], "normal")
        self.assertEqual(app.camera_button.values["text"], "Buscar cámaras")

    def test_dashboard_connected_camera_shows_name_and_type(self):
        app = self.app()
        app.show_runtime_status(RuntimeStatusDTO(
            "connected", "initialized", "loaded", "loaded", True,
            "Webcam USB Logitech", "V4L2",
        ))
        self.assertIn("Conectada", app.camera_status.values["text"])
        self.assertIn("Webcam USB Logitech", app.camera_status.values["text"])
        self.assertIn("V4L2", app.camera_status.values["text"])
        self.assertEqual(app.camera_retry_button.values["state"], "disabled")

    def test_sensitive_state_disables_all_camera_actions(self):
        app = self.app(); app._set_camera_switch_allowed(False)
        self.assertEqual(app.camera_search_button.values["state"], "disabled")
        self.assertEqual(app.camera_change_button.values["state"], "disabled")
        self.assertEqual(app.camera_retry_button.values["state"], "disabled")

    def test_selector_contains_required_sections_and_safe_url_entry(self):
        source = inspect.getsource(CameraSelectionWindow.__init__)
        for text in ("Cámaras locales detectadas", "Cámaras de red", "+ Agregar cámara IP",
                     "Probar", "Guardar", "Conectar"):
            self.assertIn(text, source)
        self.assertIn('show="•"', source)

    def test_selector_is_singleton_in_composition(self):
        source = inspect.getsource(ui_main.main)
        guard = source.index('camera_window.get("window")')
        creation = source.index("CameraSelectionWindow(", guard)
        self.assertLess(guard, creation)


if __name__ == "__main__":
    unittest.main()
