import unittest
from types import SimpleNamespace

from src.ui.contracts import EnrollmentProgressDTO, MonitoringDTO, UIState
from src.ui.form_validation import validate_registration_form
from src.ui.live_session import LiveFaceSession, SessionCommandType
from src.ui.operational_semantics import OperationalPresentationState
from src.ui.tk_app import LocalFaceTkApp, RegistrationFlowState
from src.ui.web_dashboard.controller import WebDashboardController


class _QueueOnlySession(LiveFaceSession):
    def __init__(self):
        self.commands = []
        self.suspended = []

    def _command(self, command):
        self.commands.append(command)
        return True

    def set_event_history_suspended(self, value):
        self.suspended.append(value)


class RC226EnrollmentTransitionTests(unittest.TestCase):
    def test_start_enrollment_preserves_real_person_id_in_existing_session(self):
        form = validate_registration_form(
            "Ada", "Lovelace", None, consent_confirmed=True,
            persist_locally=True, cedula="1710034065",
            id_factory=lambda: "11111111-2222-4333-8444-555555555555",
        )
        session = _QueueOnlySession()

        self.assertTrue(session.start_enrollment(form))
        self.assertEqual(session.commands[0].kind, SessionCommandType.START_ENROLLMENT)
        self.assertIs(session.commands[0].form, form)
        self.assertEqual(
            session.commands[0].form.person_id,
            "11111111-2222-4333-8444-555555555555",
        )
        self.assertEqual(session.suspended, [True])

    def test_capture_window_opens_only_after_worker_confirms_enrollment(self):
        app = LocalFaceTkApp.__new__(LocalFaceTkApp)
        app._registration_flow_state = RegistrationFlowState.STARTING_ENROLLMENT
        app._form = object()
        app._enrollment_video = None
        app._enrollment_active = False
        app._registration_form_open = True
        opened = []
        app._show_enrollment_capture = lambda form: opened.append(form)
        app._set_camera_switch_allowed = lambda _allowed: None
        app._clear_pending_popups = lambda: None
        app._identification = None
        app._identification_popup = None
        app.status = app.register_button = app.cancel_button = SimpleNamespace(
            configure=lambda **_values: None)
        progress = EnrollmentProgressDTO(
            UIState.ENROLLING, "Frontal", 0, 5, (), None, None, True,
        )

        app.show_progress(progress)

        self.assertEqual(opened, [app._form])
        self.assertIs(app._registration_flow_state, RegistrationFlowState.ENROLLMENT)

    def test_single_flow_state_blocks_unknown_popup_during_all_registration_stages(self):
        app = LocalFaceTkApp.__new__(LocalFaceTkApp)
        app._registration_form_open = False
        app._enrollment_active = False
        for state in (
            RegistrationFlowState.CIVIL_FORM,
            RegistrationFlowState.STARTING_ENROLLMENT,
            RegistrationFlowState.ENROLLMENT,
            RegistrationFlowState.PROFILE_PHOTO,
        ):
            app._registration_flow_state = state
            self.assertTrue(app._registration_flow_active())
        app._registration_flow_state = RegistrationFlowState.IDLE
        self.assertFalse(app._registration_flow_active())


class RC226WebOperationalModalTests(unittest.TestCase):
    @staticmethod
    def monitoring(state="NOT_EVALUATED"):
        return MonitoringDTO(
            UIState.NO_FACE, "Sin rostro", None, None, "NOT_EVALUATED", True,
            recognition_state=state, evaluated=False,
        )

    def projection(self, operational, state="NOT_EVALUATED"):
        controller = WebDashboardController(
            lambda: None,
            presentation_provider=lambda: self.monitoring(state),
            operational_state_provider=lambda _dto: operational,
        )
        return controller, controller.api("/api/presentation")

    def test_normal_operational_states_remain_in_api_without_blocking_modal(self):
        for operational in (
            OperationalPresentationState.NO_FACE,
            OperationalPresentationState.CAMERA_DISCONNECTED,
            OperationalPresentationState.RECOGNITION_UNAVAILABLE,
            OperationalPresentationState.GALLERY_UNREGISTERED,
        ):
            controller, value = self.projection(operational)
            self.assertFalse(value["active"])
            self.assertTrue(value["kind"])
            self.assertTrue(value["status"])
            page = controller.render("/").decode()
            self.assertIn('id="modal-overlay"', page)
            self.assertIn('id="modal-overlay" class="modal-overlay" hidden', page)

    def test_no_gallery_and_not_evaluated_are_non_blocking_but_reported(self):
        for state in ("NO_GALLERY", "NOT_EVALUATED"):
            controller = WebDashboardController(
                lambda: None, presentation_provider=lambda s=state: self.monitoring(s),
            )
            value = controller.api("/api/presentation")
            self.assertFalse(value["active"])
            self.assertEqual(value["kind"], state)
            self.assertIn(state, str(controller.dashboard_payload()))


if __name__ == "__main__":
    unittest.main()
