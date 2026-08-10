import inspect
import unittest
from datetime import date
from types import SimpleNamespace

from src.core.reports import ReportPolicy, ReportValidationError
from src.ui.reports import ReportController, ReportWindow


class Service:
    policy = ReportPolicy()
    def daily_report(self, day): return ("daily", day)
    def date_range_report(self, start, end): return ("range", start, end)
    def person_report(self, person_id, start, end): return (person_id, start, end)
    def detection_summary(self, start, end): return ("detection", start, end)
    def system_summary(self, day): return ("system", day)


class ReportWindowTests(unittest.TestCase):
    def test_controller_filters_and_last_report(self):
        controller = ReportController(Service())
        result = controller.generate("Por persona", "2026-01-01", "2026-01-02", "person")
        self.assertIs(controller.last_report, result)
        with self.assertRaises(ReportValidationError):
            controller.generate("Por persona", "2026-01-01", "2026-01-02")
        with self.assertRaises(ReportValidationError):
            controller.generate("bad", "invalid", "2026-01-02")

    def test_window_declares_singleton_focus_and_safe_formats(self):
        source = inspect.getsource(ReportWindow)
        for text in ("Reportes", "Desde", "Hasta", "Persona", "Tipo",
                     "Exportar CSV", "Exportar Excel", "Exportar PDF", "focus_force"):
            self.assertIn(text, source)
        self.assertIn('state="disabled"', source)


if __name__ == "__main__": unittest.main()
