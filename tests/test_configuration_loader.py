import json,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from src.core.configuration import *
class LoaderTests(unittest.TestCase):
 def test_valid_legacy_v1_future_and_invalid_type(self):
  with TemporaryDirectory() as d:
   root=Path(d);loader=ConfigurationLoader(ConfigurationValidator(root));path=root/"x.json"
   path.write_text('{}');self.assertTrue(loader.load(path,ConfigurationProfile.DEVELOPMENT).legacy_configuration)
   path.write_text('{"config_schema_version":1}');self.assertFalse(loader.load(path,ConfigurationProfile.DEVELOPMENT).legacy_configuration)
   for value in (2,"1"):
    path.write_text(json.dumps({"config_schema_version":value}))
    with self.assertRaises(ConfigurationError):loader.load(path,ConfigurationProfile.DEVELOPMENT)
 def test_invalid_json_and_wrong_section_type(self):
  with TemporaryDirectory() as d:
   root=Path(d);loader=ConfigurationLoader(ConfigurationValidator(root));path=root/"x.json";path.write_text('{')
   with self.assertRaises(ConfigurationError):loader.load(path,ConfigurationProfile.DEVELOPMENT)
   path.write_text('{"security":[]}')
   with self.assertRaises(ConfigurationError):loader.load(path,ConfigurationProfile.DEVELOPMENT)
