from __future__ import annotations

import inspect
import unittest

from src.ui.main import main
from src.ui.tk_app import LocalFaceTkApp


class RC222FinalDashboardTests(unittest.TestCase):
    def setUp(self):
        self.dashboard=inspect.getsource(LocalFaceTkApp.__init__)
        self.enrollment=inspect.getsource(LocalFaceTkApp._show_enrollment_capture)

    def test_final_header_and_sidebar_constraints(self):
        self.assertNotIn("MODO APPLIANCE — RED LOCAL",self.dashboard)
        self.assertIn("sidebar_width=200",self.dashboard)
        self.assertIn("else 190",self.dashboard)
        self.assertIn('style.theme_use("clam")',self.dashboard)
        self.assertNotIn("lightgray",self.dashboard.casefold())

    def test_six_kpis_video_and_operational_right_column(self):
        self.assertIn("for column in range(6)",self.dashboard)
        self.assertIn("body.columnconfigure(0, weight=65)",self.dashboard)
        self.assertIn("body.columnconfigure(1, weight=35)",self.dashboard)
        for text in ("VIDEO EN TIEMPO REAL","ESTADO DEL SISTEMA","ACCESO WEB",
                     "ESTADO DE LA CÁMARA","CAMBIAR CÁMARA"):
            self.assertIn(text,self.dashboard)
        self.assertIn("command=on_camera",self.dashboard)

    def test_lower_panels_and_safe_recognition_states(self):
        for text in ("RECONOCIMIENTOS RECIENTES","ASISTENCIA DE HOY",
                     "RENDIMIENTO DEL SISTEMA","IDENTIFICADO",
                     "NO EVALUADO","NO REGISTRADA"):
            self.assertIn(text,self.dashboard)

    def test_enrollment_remains_a_separate_rectangular_window(self):
        self.assertNotIn("REGISTRO FACIAL",self.dashboard)
        self.assertIn('form.title("REGISTRO FACIAL")',self.enrollment)
        self.assertIn('form.geometry("820x760")',self.enrollment)
        self.assertIn("self._enrollment_video=tk.Canvas",self.enrollment)
        self.assertNotIn("create_oval",self.enrollment)
        self.assertNotIn("VideoCapture",self.enrollment)

    def test_main_composition_keeps_one_shared_pipeline(self):
        source=inspect.getsource(main)
        self.assertEqual(source.count("LatestPresentationFrameStore()"),1)
        self.assertEqual(source.count("LiveFaceSession("),1)
        for construction in ("CameraManager(","RecognitionService(","Runtime("):
            self.assertNotIn(construction,self.dashboard)


if __name__ == "__main__":
    unittest.main()
