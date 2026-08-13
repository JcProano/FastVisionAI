from __future__ import annotations
import unittest
from pathlib import Path
from scripts.release_check import ROOT,run
class ReleaseCheckSmokeTests(unittest.TestCase):
 def test_read_only_release_check(self):
  ok,messages=run((ROOT/"config/local_face_validation.dev.json",ROOT/"config/local_face_validation.prod.json"));self.assertTrue(ok,"\n".join(messages))

