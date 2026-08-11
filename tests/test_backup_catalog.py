import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from src.core.backup import *
class BackupCatalogTests(unittest.TestCase):
 def test_resolves_allowlisted_sources(self):
  with TemporaryDirectory() as d:
   catalog=BackupSourceCatalog(Path(d),{"backup":{"include_configuration":False}});self.assertEqual(len(catalog.sources()),6);self.assertTrue(all(Path(d).resolve() in s.source_path.parents for s in catalog.sources()))
 def test_traversal_and_absolute_rejected(self):
  with TemporaryDirectory() as d:
   for value in ("../x","/tmp/x"):
    with self.assertRaises(BackupValidationError):BackupSourceCatalog(Path(d),{"person_database":{"path":value},"backup":{"include_configuration":False}}).sources()
