from __future__ import annotations

import inspect
import unittest

from src.ui.identification.tk_popup import IdentificationPopupWindow
from src.ui.tk_app import LocalFaceTkApp


class RC22SaasTkLayoutTests(unittest.TestCase):
    def setUp(self):
        self.init_source = inspect.getsource(LocalFaceTkApp.__init__)
        self.class_source = inspect.getsource(LocalFaceTkApp)

    def test_six_colored_kpis_are_declared(self):
        for key in (
            "present", "registered", "biometrics", "entries", "late",
            "without_face",
        ):
            self.assertIn(f'("{key}"', self.init_source)
        for color in ("Cyan", "Blue", "Green", "Orange", "Red", "Purple"):
            self.assertIn(f'("{color}"', self.init_source)
        self.assertIn("for column in range(6)", self.init_source)

    def test_video_is_main_and_registration_is_not_in_dashboard(self):
        self.assertIn('text="▦  VIDEO EN TIEMPO REAL"', self.init_source)
        self.assertNotIn('enrollment_card=', self.init_source)
        self.assertIn('right_column=ttk.Frame(body)', self.init_source)
        self.assertNotIn("create_oval", self.class_source)
        self.assertIn("self.video = tk.Canvas", self.init_source)

    def test_registration_guidance_and_progress_are_in_separate_window(self):
        source=inspect.getsource(LocalFaceTkApp._show_enrollment_capture)
        for text in (
            "REGISTRO FACIAL", "Paso 1/5 — Frontal", "RECOMENDACIONES",
            "Calidad:", "Muestras:", "CAPTURAR MUESTRA", "CANCELAR",
        ):
            self.assertIn(text, source)
        self.assertIn("form.geometry",source)
        self.assertIn("self._enrollment_video=tk.Canvas",source)
        self.assertNotIn("create_oval",source)

    def test_three_lower_operational_panels_are_present(self):
        for text in (
            "RECONOCIMIENTOS RECIENTES", "ASISTENCIA DE HOY",
            "RENDIMIENTO DEL SISTEMA", "Ver todos",
            "Ver asistencia completa", "CPU: N/D", "Memoria: N/D",
            "FPS: N/D", "Latencia: N/D", "Cámara: N/D", "IA: N/D",
            "Versión: N/D",
        ):
            self.assertIn(text, self.init_source)

    def test_sidebar_is_single_and_web_access_remains_available(self):
        self.assertEqual(self.init_source.count("sidebar_items=("), 1)
        self.assertNotIn("navigation = ttk.Frame", self.init_source)
        self.assertIn("ACCESO WEB", self.init_source)
        self.assertIn("copy_web_dashboard_url", self.init_source)
        self.assertIn("open_web_dashboard", self.init_source)
        self.assertIn("ESTADO DEL SISTEMA", self.init_source)

    def test_layout_is_responsive_from_1280_width(self):
        self.assertIn("max(1280", self.init_source)
        self.assertIn("body.columnconfigure(0, weight=65)", self.init_source)
        self.assertIn("body.columnconfigure(1, weight=35)", self.init_source)
        self.assertIn("body.rowconfigure(0, weight=3)", self.init_source)
        self.assertIn("body.rowconfigure(1,weight=2)", self.init_source)


class RC22IdentificationColorsTests(unittest.TestCase):
    def test_popup_colors_follow_semantic_state(self):
        build = inspect.getsource(IdentificationPopupWindow._build)
        render = inspect.getsource(IdentificationPopupWindow._render)
        self.assertIn('(\"Identified\", \"#32D583\")', build)
        self.assertIn('(\"Candidate\", \"#F79009\")', build)
        self.assertIn('(\"Unknown\", \"#F04438\")', build)
        self.assertIn("Identification.Identified.TLabel", render)
        self.assertIn("Identification.Candidate.TLabel", render)
        self.assertIn("Identification.Unknown.TLabel", render)


class RC221VisualParityTests(unittest.TestCase):
    def setUp(self):
        self.source = inspect.getsource(LocalFaceTkApp.__init__)

    def test_sidebar_has_bounded_responsive_width(self):
        self.assertIn("sidebar_width=200 if root.winfo_screenwidth()>=1600 else 190", self.source)
        self.assertIn("width=sidebar_width", self.source)
        self.assertIn("sidebar.grid_propagate(False)", self.source)
        self.assertIn("root.columnconfigure(0, weight=0", self.source)

    def test_navigation_is_compact_dark_and_never_legacy_gray(self):
        self.assertIn('style.theme_use("clam")', self.source)
        self.assertIn('background="#081625"', self.source)
        self.assertIn('background="#185ABD"', self.source)
        self.assertIn('padding=(12,7)', self.source)
        for legacy_gray in ("#d9d9d9", "#f0f0f0", "lightgray"):
            self.assertNotIn(legacy_gray, self.source.casefold())

    def test_visible_kpis_and_main_panels_are_modern_frames(self):
        self.assertIn('style=f"{color}.Kpi.TFrame"', self.source)
        self.assertNotIn('style=f"{color}.Kpi.TLabelframe"', self.source)
        self.assertIn('video_card = ttk.Frame(body, style="Card.TFrame"', self.source)
        self.assertNotIn('enrollment_card=', self.source)
        self.assertIn('main_health=ttk.Frame(right_column,style="Card.TFrame"',self.source)
        self.assertIn("for column in range(6)", self.source)

    def test_header_has_left_and_right_regions_without_appliance_badge(self):
        self.assertIn("column=3,rowspan=2", self.source)
        self.assertIn("column=4,rowspan=2", self.source)
        self.assertNotIn("MODO APPLIANCE — RED LOCAL", self.source)


if __name__ == "__main__":
    unittest.main()
