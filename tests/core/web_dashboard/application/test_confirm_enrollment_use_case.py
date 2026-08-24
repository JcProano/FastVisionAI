import unittest

from src.core.web_dashboard.application import (
    ConfirmWebEnrollmentUseCase,
    WebEnrollmentSession,
)
from src.core.web_dashboard.domain import WebEnrollmentStage, WebEnrollmentState


class ConfirmWebEnrollmentUseCaseTests(unittest.TestCase):
    def test_marks_a_confirmed_workflow_complete(self):
        session = WebEnrollmentSession()
        session.replace(WebEnrollmentState(WebEnrollmentStage.CONFIRMATION))

        self.assertTrue(ConfirmWebEnrollmentUseCase(session).execute())

        self.assertIs(session.current().stage, WebEnrollmentStage.COMPLETE)


if __name__ == "__main__":
    unittest.main()
