import unittest
from types import SimpleNamespace

from src.core.web_dashboard.application import (
    GetWebEnrollmentStatusUseCase,
    WebEnrollmentSession,
)
from src.core.web_dashboard.domain import WebEnrollmentStage, WebEnrollmentState


class GetWebEnrollmentStatusUseCaseTests(unittest.TestCase):
    def test_projects_progress_without_exposing_biometric_payloads(self):
        session = WebEnrollmentSession()
        session.replace(WebEnrollmentState(WebEnrollmentStage.CAPTURE))
        progress = SimpleNamespace(
            accepted_samples=3,
            target_samples=5,
            instruction="Mire al frente",
            quality_score=88.0,
            quality_band="GOOD",
            embedding=(0.1, 0.2),
        )

        payload = GetWebEnrollmentStatusUseCase(
            session, lambda: progress
        ).execute()

        self.assertEqual(payload["accepted_samples"], 3)
        self.assertEqual(payload["stage"], "CAPTURE")
        self.assertNotIn("embedding", payload)


if __name__ == "__main__":
    unittest.main()
