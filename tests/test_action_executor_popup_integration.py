import queue
import threading
import unittest
from datetime import datetime, timezone
from unittest.mock import Mock

from src.core.detection_events import DetectionEventWriteResult
from src.engine.action_executor import (
    ActionExecutionInput, ActionExecutionState, ActionExecutor, ActionExecutorPolicy,
    DetectionEventActionData, PopupActionData,
)
from src.engine.decision_orchestrator import DecisionOrchestrator, DecisionOrchestratorPolicy
from src.engine.identification_policy import (
    IdentificationPolicy, IdentificationPolicyEngine,
)
from src.engine.stability import StabilityPolicy, StabilityTracker
from src.ui.action_adapters import (
    DetectionEventServiceActionAdapter, IdentificationPopupActionAdapter,
)
from src.ui.contracts import (
    ActionExecutorDTO, DecisionOrchestratorDTO, MonitoringDTO, UIState,
)
from src.ui.identification import (
    IdentificationPopupDTO, IdentificationPopupPolicy, IdentificationPopupType,
    IdentificationPresentationController, IdentityPersonDTO,
)
from src.ui.live_session import LiveFaceSession
from src.ui.main import uses_action_executor_detection_logging, uses_action_executor_popups
from src.ui.tk_app import LocalFaceTkApp
from src.ui.thumbnails import ThumbnailDTO


class Provider:
    def get_person(self, person_id):
        return IdentityPersonDTO(person_id, "Temporary", "Person", "Temporary Person", None)
    def get_thumbnail(self, person_id):
        return ThumbnailDTO(person_id, False, 0, 0, "jpeg", None)


class EventService:
    def __init__(self, success=True): self.calls = []; self.success = success
    def observe(self, item):
        self.calls.append(item)
        return DetectionEventWriteResult(self.success, self.success, None,
                                         "recorded" if self.success else "failure")


class FailingPopup:
    def show_registered(self, _context, _popup): raise RuntimeError("controlled")
    def show_unregistered(self, _context, _popup): raise RuntimeError("controlled")


class Widget:
    def configure(self, **_values): pass


class PresentationSpy:
    def __init__(self, dto): self.dto = dto; self.calls = 0
    def observe(self, _monitoring): self.calls += 1; return self.dto
    def resume(self): pass


class WindowSpy:
    def __init__(self): self.shown = 0; self.dismissed = 0; self.popup_type = None
    def show(self, _dto): self.shown += 1
    def dismiss(self): self.dismissed += 1


def components(*, popup=True, event_success=True, frames=1, monotonic=None):
    controller_kwargs = {} if monotonic is None else {"monotonic": monotonic}
    controller = IdentificationPresentationController(
        IdentificationPopupPolicy(
            True, 0, 0, frames, 60,
            registered_popup_timeout_seconds=60,
        ),
        Provider(), **controller_kwargs,
    )
    popup_adapter = IdentificationPopupActionAdapter(controller) if popup else None
    events = EventService(event_success)
    policy = ActionExecutorPolicy(
        automatic_execution_enabled=True, allow_registered_popup=True,
        allow_unregistered_popup=True, allow_detection_event_logging=True,
    )
    action = ActionExecutor(
        policy, popup_adapter=popup_adapter,
        detection_event_adapter=DetectionEventServiceActionAdapter(events),
    )
    decision = DecisionOrchestrator(DecisionOrchestratorPolicy(
        automatic_actions_enabled=True, allow_registered_popup_proposal=True,
        allow_unregistered_popup_proposal=True, allow_detection_event_proposal=True,
        allow_attendance_proposal=False, require_stable_for_registered_popup=True,
    ))
    return controller, popup_adapter, events, action, decision


def live_session(events, action, decision):
    live = LiveFaceSession.__new__(LiveFaceSession)
    live._detection_events = events; live._event_history_suspended = threading.Event()
    live._camera_id = "mock"; live._session_id = "session"
    live._administrative_status_resolver = lambda _person: "ACTIVE"
    live._stability = StabilityTracker(StabilityPolicy(
        minimum_observations=1, minimum_duration_seconds=0,
    ))
    live._identification_policy = IdentificationPolicyEngine(IdentificationPolicy(
        require_stable_observation=True, minimum_stability_observations=1,
        minimum_stability_duration_seconds=0,
    ))
    live._decision_orchestrator = decision
    live._action_executor = action; live._detection_event_logging_via_executor = True
    live._identification_presentation = None
    live._identification_pause_active = False
    live.event_queue = queue.Queue(maxsize=50)
    return live


class ActionExecutorPopupIntegrationTests(unittest.TestCase):
    def ui(self, mode, presentation, window, requests=()):
        app = LocalFaceTkApp.__new__(LocalFaceTkApp)
        app._popup_mode = mode; app._identification = presentation
        app._identification_popup = window; app._get_popup_requests = lambda: requests
        app._registration_form_open = False; app._enrollment_active = False
        app._closing = False; app._on_registration_form_state = lambda _value: None
        for name in ("status", "candidate", "similarity", "decision", "quality",
                     "register_button"):
            setattr(app, name, Widget())
        return app

    def test_legacy_and_executor_ui_paths_are_mutually_exclusive(self):
        popup_dto = IdentificationPopupDTO(
            IdentificationPopupType.UNREGISTERED, None, None, None, None,
            "NO_GALLERY", False, "safe", datetime.now(timezone.utc),
        )
        monitoring = MonitoringDTO(
            UIState.MONITORING, "safe", None, None, "NOT_EVALUATED", True,
            recognition_state="NO_GALLERY",
        )
        legacy_controller = PresentationSpy(popup_dto); legacy_window = WindowSpy()
        legacy = self.ui("legacy", legacy_controller, legacy_window)
        legacy.show_monitoring(monitoring)
        self.assertEqual((legacy_controller.calls, legacy_window.shown), (1, 1))

        action_controller = PresentationSpy(popup_dto); action_window = WindowSpy()
        action = self.ui("action_executor", action_controller, action_window, (popup_dto,))
        action.show_monitoring(monitoring)
        action._drain_action_popups()
        self.assertEqual(action_controller.calls, 0)
        self.assertEqual(action_window.shown, 1)

    def test_legacy_ui_requires_stable_orchestrator_popup_proposal(self):
        popup_dto = IdentificationPopupDTO(
            IdentificationPopupType.UNREGISTERED, None, None, None, None,
            "UNKNOWN", False, "safe", datetime.now(timezone.utc),
        )
        controller = PresentationSpy(popup_dto); window = WindowSpy()
        app = self.ui("legacy", controller, window)
        app._decision_orchestrator = DecisionOrchestratorDTO(
            "OBSERVATION_ONLY", True, None, ("LOG_DETECTION_EVENT",),
            ("SHOW_UNREGISTERED_POPUP",),
            ("unregistered_observation_not_stable",), True, "test", "1",
        )
        app.show_monitoring(MonitoringDTO(
            UIState.MONITORING, "safe", None, .4, "NOT_EVALUATED", True,
            recognition_state="UNKNOWN",
        ))
        self.assertEqual((controller.calls, window.shown), (0, 0))

    def test_registered_and_unregistered_executor_paths_with_logging(self):
        for person_id, state, expected_popup in (
            ("person", "NOT_EVALUATED", IdentificationPopupType.REGISTERED_CANDIDATE),
            (None, "NO_GALLERY", None),
        ):
            with self.subTest(person_id=person_id):
                _, popup, events, action, decision = components()
                live = live_session(events, action, decision)
                live._emit_monitoring(MonitoringDTO(
                    UIState.MONITORING, "safe", "Temporary" if person_id else None,
                    .8 if person_id else None, "NOT_EVALUATED", True,
                    recognition_state=state, candidate_person_id=person_id,
                    evaluated=False,
                ))
                result = next(item for item in tuple(live.event_queue.queue)
                              if isinstance(item, ActionExecutorDTO))
                self.assertEqual(result.state, "EXECUTED")
                expected_actions = (("SHOW_REGISTERED_POPUP", "LOG_DETECTION_EVENT")
                                    if person_id else ("LOG_DETECTION_EVENT",))
                self.assertEqual(result.executed_actions, expected_actions)
                self.assertEqual(len(events.calls), 1)
                queued = popup.drain()
                self.assertEqual(queued[0].popup_type if queued else None, expected_popup)

    def test_registered_popup_pause_suppresses_duplicate_actions_not_matching(self):
        clock = [0.0]
        presentation, popup, events, action, decision = components(
            monotonic=lambda: clock[0],
        )
        live = live_session(events, action, decision)
        live._identification_presentation = presentation
        candidate = MonitoringDTO(
            UIState.MONITORING, "safe", "Temporary", .80,
            "NOT_EVALUATED", True, recognition_state="NOT_EVALUATED",
            candidate_person_id="person", evaluated=False,
        )

        live._emit_monitoring(candidate)
        first_actions = [
            item for item in tuple(live.event_queue.queue)
            if isinstance(item, ActionExecutorDTO)
        ]
        self.assertEqual(first_actions[-1].executed_actions,
                         ("SHOW_REGISTERED_POPUP", "LOG_DETECTION_EVENT"))
        self.assertEqual(len(popup.drain()), 1)
        self.assertEqual(len(events.calls), 1)
        self.assertEqual(presentation.registered_pause_remaining_seconds(), 60)

        live._emit_monitoring(candidate)
        paused_actions = [
            item for item in tuple(live.event_queue.queue)
            if isinstance(item, ActionExecutorDTO)
        ]
        self.assertEqual(paused_actions[-1].requested_actions, ())
        self.assertEqual(paused_actions[-1].executed_actions, ())
        self.assertEqual(popup.drain(), ())
        self.assertEqual(len(events.calls), 1)

        clock[0] = 60
        live._emit_monitoring(candidate)
        resumed_actions = [
            item for item in tuple(live.event_queue.queue)
            if isinstance(item, ActionExecutorDTO)
        ]
        self.assertEqual(resumed_actions[-1].executed_actions,
                         ("SHOW_REGISTERED_POPUP", "LOG_DETECTION_EVENT"))
        self.assertEqual(len(popup.drain()), 1)
        self.assertEqual(len(events.calls), 2)

    def test_popup_and_logging_failures_are_independent(self):
        base = dict(
            proposed_actions=("SHOW_REGISTERED_POPUP", "LOG_DETECTION_EVENT"),
            blocked_actions=(), orchestrator_state="POLICY_ELIGIBLE",
            orchestrator_automatic_actions_enabled=True, person_id="person",
            run_id="run", session_id="session", timestamp=datetime.now(timezone.utc),
            detection_event=DetectionEventActionData("NOT_EVALUATED"),
            popup=PopupActionData("NOT_EVALUATED"),
        )
        for popup_fails, logging_fails, expected in (
            (True, False, ActionExecutionState.PARTIALLY_EXECUTED),
            (False, True, ActionExecutionState.PARTIALLY_EXECUTED),
            (True, True, ActionExecutionState.FAILED),
        ):
            with self.subTest(popup=popup_fails, logging=logging_fails):
                events = EventService(not logging_fails)
                real_popup = IdentificationPopupActionAdapter(
                    IdentificationPresentationController(
                        IdentificationPopupPolicy(candidate_stability_frames=1), Provider()))
                action = ActionExecutor(
                    ActionExecutorPolicy(automatic_execution_enabled=True),
                    popup_adapter=FailingPopup() if popup_fails else real_popup,
                    detection_event_adapter=DetectionEventServiceActionAdapter(events),
                )
                self.assertEqual(action.execute(ActionExecutionInput(**base)).state, expected)
                self.assertEqual(len(events.calls), 1)

    def test_modes_are_independent_and_require_all_popup_gates(self):
        controller, popup, events, action, decision = components()
        self.assertTrue(uses_action_executor_popups(action, decision, controller))
        self.assertTrue(uses_action_executor_detection_logging(action, decision, events))
        no_popup = ActionExecutor(
            action.policy,
            detection_event_adapter=DetectionEventServiceActionAdapter(events),
        )
        self.assertFalse(uses_action_executor_popups(no_popup, decision, controller))
        self.assertTrue(uses_action_executor_detection_logging(no_popup, decision, events))
        incomplete = DecisionOrchestrator(DecisionOrchestratorPolicy(
            automatic_actions_enabled=True, allow_registered_popup_proposal=False,
            allow_unregistered_popup_proposal=True,
        ))
        self.assertFalse(uses_action_executor_popups(action, incomplete, controller))

    def test_multiple_no_face_and_incompatible_never_queue_individual_popup(self):
        for ui_state, recognition in (
            (UIState.MULTIPLE_FACES, "NOT_EVALUATED"),
            (UIState.NO_FACE, "NOT_EVALUATED"),
            (UIState.MONITORING, "INCOMPATIBLE"),
        ):
            with self.subTest(state=ui_state, recognition=recognition):
                _, popup, _, action, decision = components()
                live = live_session(EventService(), action, decision)
                live._emit_monitoring(MonitoringDTO(
                    ui_state, "safe", None, None, "NOT_EVALUATED", True,
                    recognition_state=recognition,
                ))
                self.assertEqual(popup.drain(), ())

    def test_suspension_discards_actions_and_attendance_is_never_called(self):
        _, popup, events, action, decision = components()
        live = live_session(events, action, decision); attendance = Mock()
        live.set_event_history_suspended(True)
        live._emit_monitoring(MonitoringDTO(
            UIState.MONITORING, "safe", None, None, "NOT_EVALUATED", True,
            recognition_state="NO_GALLERY",
        ))
        self.assertEqual(popup.drain(), ()); self.assertEqual(events.calls, [])
        attendance.assert_not_called()
        result = [item for item in tuple(live.event_queue.queue)
                  if isinstance(item, ActionExecutorDTO)][-1]
        self.assertEqual(result.state, "NOT_EVALUATED")


if __name__ == "__main__":
    unittest.main()
