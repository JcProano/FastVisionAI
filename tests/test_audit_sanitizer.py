from __future__ import annotations
import unittest
from pathlib import Path
from src.core.audit import AuditValidationError,sanitize_metadata,sanitize_message

class AuditSanitizerTests(unittest.TestCase):
 def test_sensitive_keys_redacted(self):
  value=sanitize_metadata({"password":"never","api_key":"never"},maximum_items=2,value_maximum_length=20);self.assertEqual(set(value.values()),{"[REDACTED]"})
 def test_deep_structures_rejected(self):
  with self.assertRaises(AuditValidationError):sanitize_metadata({"nested":{"x":1}},maximum_items=5,value_maximum_length=20)
 def test_paths_rejected_from_values(self):
  value=sanitize_metadata({"destination":"/home/private/export.csv"},maximum_items=2,value_maximum_length=30);self.assertEqual(value["destination"],"[PATH_REDACTED]")
 def test_item_limit(self):
  with self.assertRaises(AuditValidationError):sanitize_metadata({"a":1,"b":2},maximum_items=1,value_maximum_length=20)
 def test_control_and_traceback_lines_removed(self):
  self.assertEqual(sanitize_message("one\ntwo\x00",20),"one two")

