import unittest
from src.core.configuration import *
class DiffTests(unittest.TestCase):
 def test_empty_and_impact_classes(self):
  value={"dashboard":{"metrics_refresh_ms":1},"camera":{"source":0},"profile_name":"x"};self.assertFalse(configuration_diff(value,value).changes);diff=configuration_diff(value,{"dashboard":{"metrics_refresh_ms":2},"camera":{"source":1},"profile_name":"y"});self.assertEqual(len(diff.hot_reloadable),1);self.assertEqual(len(diff.restart_required),1);self.assertEqual(len(diff.immutable),1)
 def test_recursive_secret_redaction(self):
  diff=configuration_diff({"custom":{"nested":{"api_key":"old"}}},{"custom":{"nested":{"api_key":"new"}}});self.assertEqual(diff.changes[0].old_value,"[REDACTED]");self.assertEqual(redact({"x":{"private_token":"value"}})["x"]["private_token"],"[REDACTED]")
