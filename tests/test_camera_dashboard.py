from __future__ import annotations

import inspect
import unittest

from src.ui.contracts import RuntimeStatusDTO
from src.ui.tk_app import LocalFaceTkApp
from src.ui.camera_selection_window import CameraSelectionWindow, NetworkCameraDialog
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
        self.assertEqual(app.camera_button.values["state"], "normal")
        self.assertNotIn("text", app.camera_button.values)

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

    def test_selector_is_compact_and_network_form_lives_in_modal(self):
        source = inspect.getsource(CameraSelectionWindow.__init__)
        for text in ("Cámaras locales detectadas", "Cámaras de red",
                     "+ AGREGAR CÁMARA IP", "Probar", "USAR ESTA CÁMARA"):
            self.assertIn(text, source)
        self.assertNotIn("self.network_form =", source)
        modal = inspect.getsource(NetworkCameraDialog.__init__)
        self.assertIn("tk.Toplevel(parent)", modal)
        self.assertIn("self.window.transient(parent)", modal)
        self.assertIn("self.window.grab_set()", modal)
        self.assertIn('show="*" if variable is self.password', modal)

    def test_network_examples_cover_http_rtsp_and_droidcam(self):
        examples = CameraSelectionWindow.TYPE_EXAMPLES
        self.assertEqual(examples["HTTP/MJPEG"], "http://192.168.1.3:4747/video")
        self.assertEqual(examples["RTSP"], "rtsp://usuario:clave@192.168.1.100:554/stream1")
        self.assertEqual(examples["DroidCam WiFi"], "http://192.168.1.3:4747/video")

    def test_modal_supports_all_connection_types(self):
        self.assertEqual(NetworkCameraDialog.CONNECTION_TYPES,
            ("HTTP/MJPEG", "HTTPS", "RTSP", "RTSPS", "URL personalizada"))

    def test_url_validation_has_friendly_protocol_and_host_errors(self):
        with self.assertRaisesRegex(ValueError, "Debe comenzar"):
            CameraSelectionWindow.validate_camera_url("192.168.1.3/video")
        with self.assertRaisesRegex(ValueError, "Dirección de cámara inválida"):
            CameraSelectionWindow.validate_camera_url("http://")

    def test_droidcam_url_ends_in_video(self):
        self.assertEqual(
            CameraSelectionWindow.build_droidcam_url("192.168.1.3", "4747"),
            "http://192.168.1.3:4747/video",
        )

    def test_selector_is_singleton_in_composition(self):
        source = inspect.getsource(ui_main.main)
        guard = source.index('camera_window.get("window")')
        creation = source.index("CameraSelectionWindow(", guard)
        self.assertLess(guard, creation)


if __name__ == "__main__":
    unittest.main()
