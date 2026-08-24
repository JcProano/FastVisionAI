import unittest

from src.core.web_dashboard.application import (
    StartWebEnrollmentUseCase,
    SubmitWebEnrollmentPersonUseCase,
    WebEnrollmentSession,
)
from src.core.web_dashboard.domain import WebEnrollmentStage


class SubmitWebEnrollmentPersonUseCaseTests(unittest.TestCase):
    def test_delegates_civil_data_and_advances_to_preparation(self):
        session = WebEnrollmentSession()
        StartWebEnrollmentUseCase(session).execute("UNKNOWN")
        submitted = []
        use_case = SubmitWebEnrollmentPersonUseCase(
            session, lambda payload: submitted.append(payload) or "person-id"
        )

        result = use_case.execute({"first_name": "Ada", "cedula": "123"})

        self.assertEqual(result, "person-id")
        self.assertEqual(submitted[0]["first_name"], "Ada")
        self.assertIs(session.current().stage, WebEnrollmentStage.PREPARATION)
        self.assertEqual(session.current().summary["cedula"], "123")


if __name__ == "__main__":
    unittest.main()
