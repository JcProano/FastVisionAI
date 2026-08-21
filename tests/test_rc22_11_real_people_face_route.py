"""RC22.11 integration coverage for the production people-to-session route."""

from __future__ import annotations

import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import Mock, patch

from src.core.person_database import PersonCreateRequest, PersonRepository, PersonStatus
from src.engine.enrollment import EnrollmentPolicy, EnrollmentService
from src.engine.gallery import FaceGallery, FaceMatcher, MatchPolicy
from src.engine.gallery.persistence import GalleryPersistence
from src.engine.recognition import RecognitionPolicy, RecognitionService
from src.ui.contracts import EnrollmentProgressDTO, UIState
from src.ui.controller import LocalFaceUIController
from src.ui.enrollment_workflow import LocalEnrollmentWorkflow
from src.ui.live_session import LiveFaceSession
from src.ui.mock_runtime import MockUIRuntimeAdapter
from src.ui.people.controller import PeopleManagerController
from src.ui.people.database_controller import DatabasePeopleManagerController
from src.ui.people.tk_window import PeopleManagerWindow
from src.ui.recognition_session import ExperimentalRecognitionSession
from src.ui.tk_app import LocalFaceTkApp, RegistrationFlowState


def wait_until(predicate, timeout=1.5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(.005)
    return False


class RC2211RealPeopleFaceRouteTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.manifest = root / "gallery.json"
        self.archive = root / "gallery.npz"
        self.person_id = str(uuid.uuid4())
        repository = PersonRepository(root / "people.db")
        repository.initialize()
        repository.create(PersonCreateRequest(
            self.person_id, "1710034065", "Civil", "Existing",
        ))
        repository.set_status(self.person_id, PersonStatus.ACTIVE)
        self.gallery = FaceGallery()
        enrollment = EnrollmentService(self.gallery, EnrollmentPolicy(5, 5))
        matcher = FaceMatcher(policy=MatchPolicy(False, None))
        recognition = RecognitionService(
            self.gallery, matcher, RecognitionPolicy(top_k=matcher.top_k),
        )
        ui = LocalFaceUIController(
            ExperimentalRecognitionSession(recognition),
            LocalEnrollmentWorkflow(self.gallery, enrollment, 5),
        )
        biometrics = PeopleManagerController(
            self.gallery, enrollment, GalleryPersistence(enabled=True),
            self.manifest, self.archive,
        )
        self.people = DatabasePeopleManagerController(repository, biometrics)
        self.adapter = MockUIRuntimeAdapter(delay=.02)
        self.session = LiveFaceSession(
            self.adapter, ui, people_controller=self.people, event_queue_size=64,
            manual_enrollment_capture=True,
        )
        self.addCleanup(self.session.close)

    @patch("src.ui.people.tk_window.messagebox")
    def test_real_window_callback_reaches_session_and_first_progress(self, dialogs):
        self.session.start()
        self.assertTrue(wait_until(self.session.active_camera_ready))
        window = PeopleManagerWindow.__new__(PeopleManagerWindow)
        person = self.people.details(self.person_id).summary
        window.selected = Mock(return_value=person)
        window._on_replace_face = self.session.start_face_replacement
        window._on_register_face = self.session.start_existing_person_enrollment
        window._on_reactivate_person = Mock()
        window._camera_available = self.session.active_camera_ready
        window.status = Mock()
        window.window = object()
        window.refresh = Mock()
        dialogs.askyesno.return_value = True

        window.replace_face()
        seen = []
        self.assertTrue(wait_until(lambda: (
            seen.extend(self.session.drain_events()) or any(
                isinstance(event, EnrollmentProgressDTO) for event in seen
            )
        )))

        self.assertEqual(self.people.state.value, "enrolling_more")
        self.assertEqual(self.session._additional_person_id, self.person_id)
        progress = next(event for event in seen if isinstance(event, EnrollmentProgressDTO))
        self.assertEqual(progress.state, UIState.ENROLLING)
        self.assertEqual(progress.accepted_samples, 0)
        self.assertEqual(progress.target_samples, 5)
        self.assertEqual(len(self.gallery.list_identities()), 0)

        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and len(self.gallery.templates(self.person_id)) < 5:
            self.session.capture_enrollment_sample()
            time.sleep(.035)
        self.assertEqual(len(self.gallery.templates(self.person_id)), 5)
        reloaded = FaceGallery()
        GalleryPersistence(enabled=True).import_into(
            reloaded, self.manifest, self.archive,
        )
        self.assertEqual(
            [identity.person_id for identity in reloaded.list_identities()],
            [self.person_id],
        )
        self.assertEqual(len(reloaded.templates(self.person_id)), 5)

    @patch("src.ui.tk_app.tk")
    def test_first_progress_opens_registration_window_at_step_one_of_five(self, fake_tk):
        form = Mock()
        fake_tk.Toplevel.return_value = form
        app = LocalFaceTkApp.__new__(LocalFaceTkApp)
        app.root = object()
        app._form = None
        app._show_enrollment_capture = Mock()
        app._registration_flow_state = RegistrationFlowState.IDLE
        app._enrollment_active = False
        app._set_camera_switch_allowed = Mock()
        app._clear_pending_popups = Mock()
        app._identification = None
        app._identification_popup = None
        app.status = Mock(); app.register_button = Mock(); app.cancel_button = Mock()
        app._enrollment_progress = None; app._enrollment_heading = None
        app._enrollment_video = None; app._enrollment_guide_text = None
        app._enrollment_quality = None; app._enrollment_reasons = None
        app._capture_button = None
        dto = EnrollmentProgressDTO(
            UIState.ENROLLING, "Mire al frente", 0, 5, (), None, None, True,
        )

        app.show_progress(dto)

        fake_tk.Toplevel.assert_called_once_with(app.root)
        app._show_enrollment_capture.assert_called_once_with(form)
        self.assertIs(app._registration_flow_state, RegistrationFlowState.ENROLLMENT)
        app.status.configure.assert_called_with(
            text="Paso 1 de 5 — Mire al frente — 0/5"
        )


if __name__ == "__main__":
    unittest.main()
