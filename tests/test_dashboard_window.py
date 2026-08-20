from __future__ import annotations

import inspect
import unittest

from src.ui.dashboard.config_window import DashboardConfigurationWindow
from src.ui.main import main
from src.ui.tk_app import LocalFaceTkApp


class DashboardWindowTests(unittest.TestCase):
    def test_dashboard_declares_responsive_cards_actions_and_minimum_size(self):
        source = inspect.getsource(LocalFaceTkApp)
        for text in (
            "FASTVISION AI", "VIDEO EN TIEMPO REAL", "Estado del sistema",
            "Candidato experimental", "Métricas de sesión", "Historial temporal",
            "Diagnóstico", "Configuración", "minimum_width", "minimum_height",
        ):
            self.assertIn(text, source)
        refresh = inspect.getsource(LocalFaceTkApp._refresh_dashboard)
        self.assertIn("configure", refresh)
        self.assertNotIn("ttk.", refresh)

    def test_secondary_windows_are_singletons_and_configuration_is_read_only(self):
        source = inspect.getsource(main)
        self.assertIn("winfo_exists", source)
        self.assertIn("lift", source)
        self.assertIn("focus", source)
        config_source = inspect.getsource(DashboardConfigurationWindow)
        self.assertNotIn("Entry", config_source)
        self.assertNotIn("write_text", config_source)

    def test_no_automatic_identity_language_is_presented(self):
        source = inspect.getsource(LocalFaceTkApp).casefold()
        for forbidden in ("identidad confirmada", "acceso permitido", "acceso denegado"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__": unittest.main()
