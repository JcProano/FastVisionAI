from __future__ import annotations

import inspect
import unittest

from src.ui.tk_app import LocalFaceTkApp


class RC223ReferenceLayoutTests(unittest.TestCase):
    def setUp(self):
        self.source=inspect.getsource(LocalFaceTkApp.__init__)

    def test_web_access_exists_only_in_sidebar(self):
        self.assertEqual(self.source.count("web_card=ttk.Frame(sidebar"),1)
        self.assertNotIn("main_web=",self.source)
        self.assertIn("ACCESO WEB",self.source)

    def test_sidebar_has_no_system_status_card_and_is_at_most_200px(self):
        self.assertNotIn("sidebar_system=",self.source)
        self.assertIn("sidebar_width=200",self.source)
        self.assertIn("else 190",self.source)

    def test_exact_main_hierarchy_is_65_35_and_three_lower_cards(self):
        self.assertIn("body.columnconfigure(0, weight=65)",self.source)
        self.assertIn("body.columnconfigure(1, weight=35)",self.source)
        self.assertIn("main_health=",self.source)
        self.assertIn("camera_card_main=",self.source)
        self.assertIn("columnspan=2",self.source)
        for text in ("RECONOCIMIENTOS RECIENTES","ASISTENCIA DE HOY",
                     "RENDIMIENTO DEL SISTEMA"):
            self.assertIn(text,self.source)

    def test_exact_palette_and_modern_kpi_cards(self):
        for color in ("#07111D","#081625","#10263A","#23445E",
                      "#2583FF","#22D3D3","#20D67A","#9854FF",
                      "#FF9800","#EF4444"):
            self.assertIn(color,self.source)
        self.assertIn('style=f"{color}.Kpi.TFrame"',self.source)
        self.assertNotIn('style=f"{color}.Kpi.TLabelframe"',self.source)

    def test_header_video_camera_and_footer_match_required_regions(self):
        for text in ("Cámara activa","Reconocimiento","RESOLUCIÓN","CALIDAD DE CAPTURA",
                     "MUESTRAS","ESTADO DE LA CÁMARA","FastVisionAI v2.0",
                     "Instituto Superior Tecnológico Simón Bolívar"):
            self.assertIn(text,self.source)
        self.assertNotIn("MODO APPLIANCE",self.source)
        self.assertNotIn("RED LOCAL",self.source)
        self.assertNotIn("REGISTRO FACIAL",self.source)


if __name__ == "__main__":
    unittest.main()
