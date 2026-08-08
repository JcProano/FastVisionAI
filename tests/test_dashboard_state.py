from __future__ import annotations

import unittest
from datetime import datetime, timezone

from src.ui.contracts import MonitoringDTO, UIState
from src.ui.dashboard.state import DashboardStateStore


class DashboardStateTests(unittest.TestCase):
    def setUp(self):
        self.clock = [0.0]
        self.store = DashboardStateStore(
            3, 2.0, monotonic=lambda: self.clock[0],
            utcnow=lambda: datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

    def monitoring(self, message, candidate=None, state="NOT_EVALUATED"):
        return MonitoringDTO(
            UIState.MONITORING, message, candidate, .9 if candidate else None,
            "NOT_EVALUATED", True, 80.0, "good", state,
        )

    def test_candidate_appears_changes_disappears_and_debounces(self):
        self.store.consume(self.monitoring("Candidato experimental", "Temporary A"))
        self.clock[0] = .5
        self.store.consume(self.monitoring("Candidato experimental", "Temporary A"))
        self.assertEqual(len(self.store.history), 1)
        self.store.consume(self.monitoring("Candidato experimental", "Temporary B"))
        self.store.consume(self.monitoring("No se detectó un rostro"))
        self.assertEqual([item.event_type for item in self.store.history], [
            "candidate", "candidate", "candidate_disappeared",
        ])

    def test_no_gallery_incompatible_and_history_limit(self):
        self.store.consume(self.monitoring("Sin candidatos registrados", state="NO_GALLERY"))
        self.store.consume(self.monitoring("Sin candidatos compatibles", state="INCOMPATIBLE"))
        self.store.consume(self.monitoring("Candidato experimental", "A"))
        self.store.consume(self.monitoring("Candidato experimental", "B"))
        self.assertEqual(len(self.store.history), 3)
        self.assertEqual(self.store.history[-1].display_name, "B")
        self.assertIn("incompatible", [item.event_type for item in self.store.history])


if __name__ == "__main__": unittest.main()
