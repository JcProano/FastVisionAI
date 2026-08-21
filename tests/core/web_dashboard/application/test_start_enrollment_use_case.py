import unittest

from src.core.web_dashboard.application import (
    StartWebEnrollmentUseCase,
    WebEnrollmentSession,
)
from src.core.web_dashboard.domain import WebEnrollmentError, WebEnrollmentStage


class StartWebEnrollmentUseCaseTests(unittest.TestCase):
    def test_starts_only_for_an_unregistered_presentation(self):
        session = WebEnrollmentSession()
        use_case = StartWebEnrollmentUseCase(session)

        state = use_case.execute("UNKNOWN")

        self.assertIs(state.stage, WebEnrollmentStage.PERSON)
        with self.assertRaises(WebEnrollmentError):
            use_case.execute("MATCH")


if __name__ == "__main__":
    unittest.main()
