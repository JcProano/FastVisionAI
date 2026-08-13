import inspect,unittest
from src.ui.configuration import ConfigurationWindow
class WindowTests(unittest.TestCase):
 def test_singleton_compatible_legacy_and_impact_language(self):
  source=inspect.getsource(ConfigurationWindow);self.assertIn("def focus",source);self.assertIn("formato legado",source);self.assertIn("reinicio",source);self.assertIn("inmutables",source);self.assertIn("no aplicado",source)
 def test_ui_has_approved_actions(self):
  source=inspect.getsource(ConfigurationWindow)
  for label in ("Validar","Guardar","Recargar","Restaurar valores cargados","Importar","Exportar","Cerrar"):self.assertIn(label,source)
