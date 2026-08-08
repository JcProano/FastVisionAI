from __future__ import annotations

import inspect
import unittest

from src.ui.people.tk_window import PeopleManagerWindow


class PeopleManagerWindowTests(unittest.TestCase):
    def test_window_declares_required_safe_actions_without_opencv(self):
        source = inspect.getsource(PeopleManagerWindow)
        for label in (
            "Personas registradas", "Buscar", "Nombre", "Apellido", "Identificador",
            "Templates", "Calidad", "Editar", "Eliminar", "Agregar muestras",
            "Refrescar", "Guardar cambios", "Importar", "Exportar",
        ):
            self.assertIn(label, source)
        self.assertNotIn("cv2", source)
        self.assertNotIn("embedding", source.casefold())


if __name__ == "__main__":
    unittest.main()
