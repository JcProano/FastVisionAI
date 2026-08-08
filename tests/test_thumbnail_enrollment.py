import tempfile
import time
import unittest
from pathlib import Path

from src.engine.enrollment import EnrollmentPolicy, EnrollmentService
from src.engine.gallery import FaceGallery, FaceMatcher, MatchPolicy
from src.engine.recognition import RecognitionPolicy, RecognitionService
from src.ui.controller import LocalFaceUIController
from src.ui.enrollment_workflow import LocalEnrollmentWorkflow
from src.ui.form_validation import validate_registration_form
from src.ui.live_session import LiveFaceSession
from src.ui.mock_runtime import MockUIRuntimeAdapter
from src.ui.recognition_session import ExperimentalRecognitionSession
from src.ui.thumbnails import ThumbnailManager


def controller(gallery: FaceGallery, target: int = 3) -> LocalFaceUIController:
    recognition = RecognitionService(
        gallery, FaceMatcher(policy=MatchPolicy()), RecognitionPolicy(top_k=3),
    )
    enrollment = EnrollmentService(gallery, EnrollmentPolicy(min_templates=target,
                                                              max_templates=target))
    return LocalFaceUIController(
        ExperimentalRecognitionSession(recognition),
        LocalEnrollmentWorkflow(gallery, enrollment, target_samples=target),
    )


class FailingThumbnailManager(ThumbnailManager):
    def save(self, *args, **kwargs):
        raise OSError("controlled")


class ThumbnailEnrollmentTests(unittest.TestCase):
    def test_enrolled_with_consent_saves_thumbnail_and_failure_keeps_gallery(self):
        for failing in (False, True):
            with self.subTest(failing=failing), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); gallery = FaceGallery(); ui = controller(gallery)
                cls = FailingThumbnailManager if failing else ThumbnailManager
                thumbnails = cls(root, Path("visual"))
                session = LiveFaceSession(
                    MockUIRuntimeAdapter(delay=.001, thumbnail_capture_enabled=True), ui,
                    thumbnail_manager=thumbnails, event_queue_size=64,
                )
                session.start()
                form = validate_registration_form(
                    "Temporary", "Person", None, consent_confirmed=True,
                    persist_locally=False,
                    id_factory=lambda: "person_thumbnail",
                )
                self.assertTrue(session.start_enrollment(form))
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline and not gallery.templates():
                    time.sleep(.01)
                session.close()
                self.assertEqual(len(gallery.templates()), 3)
                self.assertEqual(thumbnails.exists("person_thumbnail"), not failing)

    def test_cancel_cleans_temporary_samples_without_artifact(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); gallery = FaceGallery(); ui = controller(gallery, 5)
            thumbnails = ThumbnailManager(root, Path("visual"))
            session = LiveFaceSession(
                MockUIRuntimeAdapter(delay=.03, thumbnail_capture_enabled=True), ui,
                thumbnail_manager=thumbnails,
            )
            session.start()
            form = validate_registration_form(
                "Temporary", "Cancel", None, consent_confirmed=True,
                persist_locally=False,
                id_factory=lambda: "person_cancel_thumbnail",
            )
            session.start_enrollment(form); time.sleep(.04); session.cancel_enrollment()
            time.sleep(.04); session.close()
            self.assertFalse((root / "visual").exists())
            self.assertFalse(gallery.templates())


if __name__ == "__main__":
    unittest.main()
