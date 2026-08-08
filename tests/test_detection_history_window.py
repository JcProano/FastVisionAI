import inspect
import unittest
from src.ui.detection_history.tk_window import DetectionHistoryWindow
from src.ui.tk_app import LocalFaceTkApp


class DetectionHistoryWindowTests(unittest.TestCase):
    def test_window_filters_export_and_dashboard_panel_are_declared(self):
        source = inspect.getsource(DetectionHistoryWindow)
        for text in ("Historial de detecciones", "Desde YYYY-MM-DD", "Hasta YYYY-MM-DD",
                     "Person ID", "Nombre", "Tipo", "Límite", "Refrescar", "Exportar CSV"):
            self.assertIn(text, source)
        dashboard = inspect.getsource(LocalFaceTkApp)
        self.assertIn("Últimos eventos", dashboard)
        self.assertIn("_get_detection_events", dashboard)


if __name__ == "__main__": unittest.main()
