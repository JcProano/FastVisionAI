import dataclasses,unittest
from src.core.configuration import *
class ContractTests(unittest.TestCase):
 def test_snapshot_is_deeply_immutable(self):
  value={"camera":{"source":0},"people_search":{"allowed_page_sizes":[25]}};snapshot=ConfigurationSnapshot(ConfigurationProfile.DEVELOPMENT,1,False,freeze(value),"x")
  with self.assertRaises(TypeError):snapshot.sections["camera"]["source"]=1
  self.assertIsInstance(snapshot.sections["people_search"]["allowed_page_sizes"],tuple);copy=snapshot.as_mapping();copy["camera"]["source"]=9;self.assertEqual(snapshot.sections["camera"]["source"],0)
 def test_public_dtos_have_no_sensitive_fields(self):
  forbidden={"password","secret","token","absolute_path","repository","model"}
  for cls in (ConfigurationSnapshot,ConfigurationValidationResult,ConfigurationChangeDTO,ConfigurationDiffDTO,ConfigurationOperationResult):self.assertFalse({f.name for f in dataclasses.fields(cls)}&forbidden)
