from __future__ import annotations

import json
import unittest
from pathlib import Path

from src.ui.main import build_dashboard_configuration


class DashboardConfigurationTests(unittest.TestCase):
    def test_effective_configuration_is_safe_and_read_only_data(self):
        settings = json.loads(Path("config/local_face_validation.dev.json").read_text(
            encoding="utf-8"
        ))
        dto = build_dashboard_configuration(settings)
        self.assertEqual(dto.source, "0")
        self.assertEqual(dto.resolution, "N/D")
        self.assertFalse(dto.automatic_decision_enabled)
        self.assertEqual(dto.match_threshold, "N/D")
        self.assertEqual(dto.ambiguity_margin, "N/D")


if __name__ == "__main__": unittest.main()
