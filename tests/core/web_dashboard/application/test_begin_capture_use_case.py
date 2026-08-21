import unittest

from src.core.web_dashboard.application import (
    BeginWebEnrollmentCaptureUseCase,
    WebEnrollmentSession,
)
from src.core.web_dashboard.domain import WebEnrollmentStage, WebEnrollmentState


class BeginWebEnrollmentCaptureUseCaseTests(unittest.TestCase):
    def test_delegates_capture_and_advances_to_capture(self):
        session = WebEnrollmentSession()
        session.replace(WebEnrollmentState(WebEnrollmentStage.PREPARATION))
        captured = []
        use_case = BeginWebEnrollmentCaptureUseCase(
            session, lambda payload: captured.append(payload) or True
        )

        self.assertTrue(use_case.execute({"manual": True}))

        self.assertEqual(captured, [{"manual": True}])
        self.assertIs(session.current().stage, WebEnrollmentStage.CAPTURE)


if __name__ == "__main__":
    unittest.main()
