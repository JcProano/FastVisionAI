from __future__ import annotations
import csv,tempfile,unittest
from datetime import datetime,timezone
from pathlib import Path
from src.core.audit import *

class AuditExporterTests(unittest.TestCase):
 def test_csv_is_safe_deterministic_and_excludes_metadata(self):
  with tempfile.TemporaryDirectory() as name:
   path=Path(name)/"audit.csv";item=AuditRecord("id",datetime.now(timezone.utc),"=actor","ADMIN",AuditAction.REPORT_EXPORTED,AuditEntityType.REPORT,None,True,"+formula","test",None,{"private":"omitted"})
   self.assertEqual(AuditCSVExporter().export((item,),path),1)
   with path.open(encoding="utf-8") as stream:rows=list(csv.reader(stream))
   self.assertNotIn("metadata_json",rows[0]);self.assertEqual(rows[1][3],"'=actor");self.assertEqual(rows[1][7],"'+formula")
 def test_no_overwrite_by_default(self):
  with tempfile.TemporaryDirectory() as name:
   path=Path(name)/"audit.csv";path.write_text("existing",encoding="utf-8")
   with self.assertRaises(AuditExportError):AuditCSVExporter().export((),path)
