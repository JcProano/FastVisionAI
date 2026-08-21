import unittest

from src.core.web_dashboard.application import (
    SelectWebEnrollmentPhotoUseCase,
    WebEnrollmentSession,
)
from src.core.web_dashboard.domain import WebEnrollmentStage, WebEnrollmentState


class SelectWebEnrollmentPhotoUseCaseTests(unittest.TestCase):
    def test_skip_advances_without_calling_photo_adapters(self):
        session = WebEnrollmentSession()
        session.replace(WebEnrollmentState(WebEnrollmentStage.PHOTO))
        calls = []
        use_case = SelectWebEnrollmentPhotoUseCase(
            session,
            start=lambda payload: calls.append("start"),
            capture=lambda payload: calls.append("capture"),
            confirm=lambda payload: calls.append("confirm"),
        )

        self.assertTrue(use_case.execute("SKIP", {}))

        self.assertEqual(calls, [])
        self.assertIs(session.current().stage, WebEnrollmentStage.CONFIRMATION)

    def test_take_capture_and_confirm_have_explicit_stages(self):
        session = WebEnrollmentSession()
        session.replace(WebEnrollmentState(WebEnrollmentStage.PHOTO))
        calls = []
        use_case = SelectWebEnrollmentPhotoUseCase(
            session,
            start=lambda payload: calls.append("start") or True,
            capture=lambda payload: calls.append("capture") or True,
            confirm=lambda payload: calls.append("confirm") or True,
        )

        use_case.execute("TAKE", {})
        self.assertIs(session.current().stage, WebEnrollmentStage.PHOTO_CAPTURE)
        use_case.execute("CAPTURE", {})
        self.assertIs(
            session.current().stage, WebEnrollmentStage.PHOTO_CONFIRMATION
        )
        use_case.execute("CONFIRM", {})

        self.assertEqual(calls, ["start", "capture", "confirm"])
        self.assertIs(session.current().stage, WebEnrollmentStage.CONFIRMATION)


if __name__ == "__main__":
    unittest.main()
