from __future__ import annotations

import inspect
import unittest
from pathlib import Path

from src.ui.main import main
from src.ui.tk_app import LocalFaceTkApp


class RC211TkLayoutTests(unittest.TestCase):
    def setUp(self):
        self.source = inspect.getsource(LocalFaceTkApp.__init__)

    def test_legacy_horizontal_navigation_is_absent(self):
        self.assertNotIn("navigation = ttk.Frame", self.source)
        self.assertNotIn("navigation_buttons", self.source)
        self.assertNotIn("nav_items", self.source)

    def test_legacy_bottom_action_bar_is_absent(self):
        self.assertNotIn("actions.grid(row=3", self.source)
        for label in ("Registrar rostro", "Personas registradas", "Copias de seguridad"):
            self.assertNotIn(f'text="{label}"', self.source)

    def test_sidebar_is_the_single_navigation_surface(self):
        for label in (
            "Dashboard", "Cámara", "Personas", "Asistencia", "Historial",
            "Reportes", "Backups", "Auditoría", "Diagnóstico", "Configuración",
        ):
            self.assertIn(f'"{label}"', self.source)
        for callback in (
            "on_camera", "on_people", "on_attendance_history", "on_detection_history",
            "on_reports", "on_backup", "on_audit", "on_system_health", "on_configuration",
        ):
            self.assertIn(callback, self.source)
        active = inspect.getsource(LocalFaceTkApp._activate_sidebar)
        self.assertIn('key == label', active)
        self.assertIn('callback()', active)

    def test_logo_is_visible_proportional_and_institution_name_is_not_duplicated(self):
        logo = Path("src/ui/assets/LOGO-MODIFICADO-SUPERIOR-izq-1.png")
        self.assertTrue(logo.is_file())
        self.assertIn("math.ceil(logo.height()/54)", self.source)
        self.assertIn('text="Instituto Superior Tecnológico Simón Bolívar"', self.source)

    def test_appliance_mode_is_not_exposed_in_the_final_header(self):
        self.assertNotIn('style="Appliance.TLabel"', self.source)
        self.assertNotIn("MODO APPLIANCE — RED LOCAL", self.source)

    def test_1280_width_and_web_dashboard_remain_supported(self):
        self.assertIn("max(1280", self.source)
        self.assertIn("ACCESO WEB", self.source)
        self.assertIn("copy_web_dashboard_url", self.source)
        self.assertIn("open_web_dashboard", self.source)

    def test_disconnected_camera_does_not_open_selector_automatically(self):
        startup = inspect.getsource(main)
        self.assertNotIn("root.after(0, open_camera_selection)", startup)


if __name__ == "__main__":
    unittest.main()
