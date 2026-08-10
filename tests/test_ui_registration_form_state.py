import inspect
import unittest

from src.ui.contracts import (
    EnrollmentProgressDTO, EnrollmentResultDTO, MonitoringDTO, UIState,
)
from src.ui.tk_app import LocalFaceTkApp
from src.ui.identification import IdentificationPopupType


class _Widget:
    def __init__(self): self.values = {}
    def configure(self, **values): self.values.update(values)


class _Identification:
    def __init__(self): self.suspended = 0; self.resumed = 0; self.observed = 0
    def suspend(self): self.suspended += 1
    def resume(self): self.resumed += 1
    def observe(self, _dto):
        self.observed += 1
        return type("Popup", (), {"popup_type": IdentificationPopupType.SUPPRESSED})()


class _Popup:
    def __init__(self): self.dismissed = 0; self.shown = 0
    def dismiss(self): self.dismissed += 1
    def show(self, _dto): self.shown += 1


class RegistrationFormPresentationTests(unittest.TestCase):
    def app(self):
        app = LocalFaceTkApp.__new__(LocalFaceTkApp)
        app._identification = _Identification(); app._identification_popup = _Popup()
        app._registration_form_open = False; app._enrollment_active = False; app._closing = False
        app._on_registration_form_state = lambda _value: None
        app._popup_mode = "action_executor"; app._get_popup_requests = lambda: ()
        app.popup_clears = 0
        def clear(): app.popup_clears += 1
        app._clear_popup_requests = clear
        for name in ("status", "candidate", "similarity", "decision", "quality",
                     "register_button", "cancel_button"):
            setattr(app, name, _Widget())
        return app

    @staticmethod
    def monitoring(person_id=None):
        return MonitoringDTO(
            UIState.MONITORING, "event", "Candidate" if person_id else None,
            .9 if person_id else None, "NOT_EVALUATED", True,
            recognition_state="NOT_EVALUATED" if person_id else "NO_GALLERY",
            candidate_person_id=person_id,
        )

    def test_form_open_suspends_and_ignores_unknown_registered_and_queued_events(self):
        app = self.app(); app._enter_registration_form_state()
        self.assertTrue(app._registration_form_open)
        self.assertEqual((app._identification.suspended, app._identification_popup.dismissed), (1, 1))
        app.show_monitoring(self.monitoring())
        app.show_monitoring(self.monitoring("person-safe"))
        app.show_monitoring(self.monitoring())  # already queued before FORM_OPEN is harmless
        self.assertEqual(app._identification.observed, 0)
        self.assertEqual(app._identification_popup.shown, 0)
        self.assertGreaterEqual(app.popup_clears, 1)

    def test_form_cancel_or_window_close_reactivates_without_reservation_callback(self):
        app = self.app(); app._enter_registration_form_state()
        app._leave_registration_form_state(resume=True)
        self.assertFalse(app._registration_form_open)
        self.assertEqual(app._identification.resumed, 1)
        self.assertGreaterEqual(app.popup_clears, 2)
        source = inspect.getsource(LocalFaceTkApp.open_form)
        self.assertIn('form.protocol(', source)
        self.assertIn('"WM_DELETE_WINDOW"', source)
        self.assertIn("close_form", source)

    def test_enrollment_keeps_suspension_until_result_or_cancel_monitoring(self):
        app = self.app(); app._enter_registration_form_state()
        app._registration_form_open = False; app._enrollment_active = True
        progress = EnrollmentProgressDTO(UIState.ENROLLING, "Frontal", 0, 5, (), None, None, True)
        app.show_progress(progress)
        self.assertEqual(app._identification.resumed, 0)
        app.show_monitoring(MonitoringDTO(
            UIState.NO_FACE, "queued", None, None, "NOT_EVALUATED", True,
            recognition_state="NO_GALLERY",
        ))
        self.assertEqual(app._identification.observed, 0)
        result = EnrollmentResultDTO(
            UIState.ENROLLMENT_COMPLETE, "person-safe", "A", "B", "A B",
            5, 0, 80, 70, 90, "enrolled", False, None, "done",
        )
        app.show_result(result)
        self.assertEqual(app._identification.resumed, 1)

        app._enrollment_active = True; app._identification.suspended += 1
        app.show_monitoring(self.monitoring())  # worker confirmation after rollback/cancel
        self.assertFalse(app._enrollment_active)
        self.assertEqual(app._identification.resumed, 2)

    def test_double_open_guard_precedes_form_creation(self):
        source = inspect.getsource(LocalFaceTkApp.open_form)
        guard = source.index("self._form.winfo_exists()")
        creation = source.index("tk.Toplevel")
        self.assertLess(guard, creation)

    def test_queued_popup_is_discarded_during_form_and_not_revived(self):
        app = self.app()
        queued = [type("PopupDTO", (), {"popup_type": IdentificationPopupType.UNREGISTERED})()]
        app._get_popup_requests = lambda: tuple(queued)
        app._enter_registration_form_state()
        app._drain_action_popups()
        self.assertEqual(app._identification_popup.shown, 0)
        queued.clear()
        app._leave_registration_form_state(resume=True)
        app._drain_action_popups()
        self.assertEqual(app._identification_popup.shown, 0)


if __name__ == "__main__":
    unittest.main()
