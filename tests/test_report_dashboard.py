import inspect
import unittest

from src.ui.main import build_reports
from src.ui.tk_app import LocalFaceTkApp


class Root:
    def __init__(self): self.calls = {}; self.cancelled = []
    def after(self, delay, callback): self.calls["report"] = (delay, callback); return "report"
    def after_cancel(self, identifier): self.cancelled.append(identifier)


class Label:
    def __init__(self): self.text = None
    def configure(self, **values): self.text = values.get("text")


class ReportDashboardTests(unittest.TestCase):
    def test_disabled_builder_does_not_construct_service(self):
        self.assertIsNone(build_reports({"reports": {"enabled": False}}, None, None, None))

    def test_refresh_is_independent_not_per_frame_and_close_cancels_timer(self):
        source = inspect.getsource(LocalFaceTkApp.poll_session)
        self.assertNotIn("_get_daily_report()", source)
        app = LocalFaceTkApp.__new__(LocalFaceTkApp); app.root = Root()
        app._closing = False; app._report_refresh_seconds = 30
        app._get_daily_report = lambda: None; app._report_after_id = None
        app._schedule_report_refresh(initial=True)
        self.assertEqual(app.root.calls["report"][0], 30_000)
        app._closing = True; app.root.after_cancel(app._report_after_id)
        self.assertEqual(app.root.cancelled, ["report"])

    def test_dashboard_has_today_card_and_safe_failure_projection(self):
        source = inspect.getsource(LocalFaceTkApp)
        for text in ("Hoy", "Personas activas", "Detecciones", "Entradas",
                     "Salidas", "Personas únicas", "Ver reportes", "N/D"):
            self.assertIn(text, source)


if __name__ == "__main__": unittest.main()
