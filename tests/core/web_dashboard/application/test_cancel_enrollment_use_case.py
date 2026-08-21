import unittest

from src.core.web_dashboard.application import (
    CancelWebEnrollmentUseCase,
    WebEnrollmentSession,
)
from src.core.web_dashboard.domain import WebEnrollmentStage, WebEnrollmentState


class CancelWebEnrollmentUseCaseTests(unittest.TestCase):
    def test_rolls_back_adapter_and_resets_session(self):
        session = WebEnrollmentSession()
        session.replace(WebEnrollmentState(WebEnrollmentStage.CAPTURE))
        cancelled = []
        use_case = CancelWebEnrollmentUseCase(
            session, lambda payload: cancelled.append(payload) or True
        )

        self.assertTrue(use_case.execute({"reason": "user"}))

        self.assertEqual(cancelled, [{"reason": "user"}])
        self.assertIs(session.current().stage, WebEnrollmentStage.IDLE)


if __name__ == "__main__":
    unittest.main()
