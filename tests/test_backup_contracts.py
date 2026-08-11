import dataclasses,unittest
from datetime import datetime,timezone
from src.core.backup import *
class BackupContractTests(unittest.TestCase):
 def test_manifest_is_safe_and_versioned(self):
  item=BackupFileEntry("x.db","components/x.db",BackupComponentType.PEOPLE_DATABASE,3,"a"*64,1,datetime.now(timezone.utc));manifest=BackupManifest(1,datetime.now(timezone.utc),"FastVisionAI","test","id","NONE",(item,),())
  self.assertEqual(manifest.encryption,"NONE");self.assertEqual(item.schema_version,1)
 def test_dtos_exclude_payloads_and_secrets(self):
  forbidden={"password","password_hash","salt","embedding","thumbnail_bytes","connection","payload"}
  for cls in (BackupResult,BackupVerificationResult,RestoreResult,BackupOperationRecord):self.assertFalse({f.name for f in dataclasses.fields(cls)}&forbidden)
