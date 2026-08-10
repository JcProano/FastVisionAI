import queue
import threading
import unittest
from unittest.mock import Mock

from src.core.detection_events import DetectionEventWriteResult
from src.engine.action_executor import ActionExecutor, ActionExecutorPolicy
from src.engine.decision_orchestrator import (
    DecisionOrchestrator, DecisionOrchestratorPolicy,
)
from src.ui.action_adapters import DetectionEventServiceActionAdapter
from src.ui.contracts import ActionExecutorDTO, MonitoringDTO, UIState
from src.ui.live_session import LiveFaceSession
from src.ui.main import uses_action_executor_detection_logging


class ServiceSpy:
    def __init__(self, success=True): self.calls = []; self.success = success
    def observe(self, item):
        self.calls.append(item)
        return DetectionEventWriteResult(self.success, self.success, None,
                                         "recorded" if self.success else "persistence_error")


def executor(service, **changes):
    values = dict(
        automatic_execution_enabled=True, allow_registered_popup=False,
        allow_unregistered_popup=False, allow_detection_event_logging=True,
    )
    values.update(changes)
    return ActionExecutor(ActionExecutorPolicy(**values),
                          detection_event_adapter=DetectionEventServiceActionAdapter(service))


def orchestrator(**changes):
    values = dict(
        automatic_actions_enabled=True, allow_registered_popup_proposal=False,
        allow_unregistered_popup_proposal=False, allow_detection_event_proposal=True,
        allow_attendance_proposal=False,
    )
    values.update(changes)
    return DecisionOrchestrator(DecisionOrchestratorPolicy(**values))


def session(service, action_executor=None, decision=None, via=False):
    value = LiveFaceSession.__new__(LiveFaceSession)
    value._detection_events = service
    value._event_history_suspended = threading.Event()
    value._camera_id = "mock"; value._session_id = "session"
    value._administrative_status_resolver = None
    value._stability = None; value._identification_policy = None
    value._decision_orchestrator = decision
    value._action_executor = action_executor
    value._detection_event_logging_via_executor = via
    value.event_queue = queue.Queue(maxsize=30)
    return value


class ActionExecutorDetectionIntegrationTests(unittest.TestCase):
    def test_legacy_and_executor_each_call_service_exactly_once(self):
        monitoring = MonitoringDTO(
            UIState.MONITORING, "unknown", None, None, "NOT_EVALUATED", True,
            recognition_state="NO_GALLERY",
        )
        legacy_service = ServiceSpy()
        session(legacy_service)._emit_monitoring(monitoring)
        self.assertEqual(len(legacy_service.calls), 1)

        action_service = ServiceSpy(); action = executor(action_service)
        live = session(action_service, action, orchestrator(), via=True)
        live._emit_monitoring(monitoring)
        self.assertEqual(len(action_service.calls), 1)
        result = next(item for item in tuple(live.event_queue.queue)
                      if isinstance(item, ActionExecutorDTO))
        self.assertEqual(result.state, "EXECUTED")
        self.assertEqual(result.executed_actions, ("LOG_DETECTION_EVENT",))

    def test_no_face_and_suspension_never_call_either_path(self):
        service = ServiceSpy(); live = session(service, executor(service), orchestrator(), True)
        live._emit_monitoring(MonitoringDTO(
            UIState.NO_FACE, "none", None, None, "NOT_EVALUATED", True,
        ))
        self.assertEqual(service.calls, [])
        live.set_event_history_suspended(True)
        live._emit_monitoring(MonitoringDTO(
            UIState.MONITORING, "unknown", None, None, "NOT_EVALUATED", True,
            recognition_state="NO_GALLERY",
        ))
        self.assertEqual(service.calls, [])
        results = [item for item in tuple(live.event_queue.queue)
                   if isinstance(item, ActionExecutorDTO)]
        self.assertEqual(results[-1].state, "NOT_EVALUATED")

    def test_form_enrollment_and_rollback_each_remain_suspended(self):
        observation = MonitoringDTO(
            UIState.MONITORING, "unknown", None, None, "NOT_EVALUATED", True,
            recognition_state="NO_GALLERY",
        )
        for phase in ("FORM_OPEN", "ENROLLING", "ROLLBACK"):
            with self.subTest(phase=phase):
                service = ServiceSpy()
                live = session(service, executor(service), orchestrator(), True)
                live.set_event_history_suspended(True)
                live._emit_monitoring(observation)
                self.assertEqual(service.calls, [])
                results = [item for item in tuple(live.event_queue.queue)
                           if isinstance(item, ActionExecutorDTO)]
                self.assertEqual(results[-1].state, "NOT_EVALUATED")

    def test_repository_failure_is_isolated_as_failed(self):
        service = ServiceSpy(False); live = session(service, executor(service), orchestrator(), True)
        live._emit_monitoring(MonitoringDTO(
            UIState.MONITORING, "unknown", None, None, "NOT_EVALUATED", True,
            recognition_state="NO_GALLERY",
        ))
        result = next(item for item in tuple(live.event_queue.queue)
                      if isinstance(item, ActionExecutorDTO))
        self.assertEqual(result.state, "FAILED")
        self.assertEqual(result.failed_actions, ("LOG_DETECTION_EVENT",))
        self.assertEqual(len(service.calls), 1)

    def test_mode_resolution_requires_every_gate_and_is_stable(self):
        service = ServiceSpy(); active_executor = executor(service); active_orch = orchestrator()
        self.assertTrue(uses_action_executor_detection_logging(
            active_executor, active_orch, service))
        self.assertFalse(uses_action_executor_detection_logging(None, active_orch, service))
        self.assertFalse(uses_action_executor_detection_logging(
            ActionExecutor(ActionExecutorPolicy(automatic_execution_enabled=True)),
            active_orch, service))
        self.assertFalse(uses_action_executor_detection_logging(
            active_executor, orchestrator(automatic_actions_enabled=False), service))
        self.assertFalse(uses_action_executor_detection_logging(
            executor(service, automatic_execution_enabled=False), active_orch, service))

    def test_each_incomplete_configuration_uses_legacy_once(self):
        observation = MonitoringDTO(
            UIState.MONITORING, "unknown", None, None, "NOT_EVALUATED", True,
            recognition_state="NO_GALLERY",
        )
        configurations = (
            (None, orchestrator()),
            (ActionExecutor(
                ActionExecutorPolicy(enabled=False),
                detection_event_adapter=DetectionEventServiceActionAdapter(ServiceSpy()),
            ), orchestrator()),
            (ActionExecutor(ActionExecutorPolicy(automatic_execution_enabled=True)),
             orchestrator()),
            (executor(ServiceSpy()), orchestrator(automatic_actions_enabled=False)),
        )
        for action, decision in configurations:
            with self.subTest(action=action, decision=decision.policy.automatic_actions_enabled):
                service = ServiceSpy()
                via = uses_action_executor_detection_logging(action, decision, service)
                self.assertFalse(via)
                session(service, action, decision, via)._emit_monitoring(observation)
                self.assertEqual(len(service.calls), 1)

    def test_repeated_evaluations_use_one_route_each_time(self):
        service = ServiceSpy(); live = session(service, executor(service), orchestrator(), True)
        observation = MonitoringDTO(
            UIState.MONITORING, "unknown", None, None, "NOT_EVALUATED", True,
            recognition_state="NO_GALLERY",
        )
        live._emit_monitoring(observation)
        live._emit_monitoring(observation)
        self.assertEqual(len(service.calls), 2)

    def test_popup_and_attendance_are_never_invoked(self):
        service = ServiceSpy(); popup = Mock(); attendance = Mock()
        action = ActionExecutor(
            ActionExecutorPolicy(
                automatic_execution_enabled=True, allow_registered_popup=False,
                allow_unregistered_popup=False, allow_detection_event_logging=True,
            ), popup_adapter=popup,
            detection_event_adapter=DetectionEventServiceActionAdapter(service),
        )
        live = session(service, action, orchestrator(), True)
        live._emit_monitoring(MonitoringDTO(
            UIState.MONITORING, "candidate", "Temporary", .8, "NOT_EVALUATED", True,
            recognition_state="NOT_EVALUATED", candidate_person_id="person",
        ))
        self.assertEqual(len(service.calls), 1)
        popup.show_registered.assert_not_called()
        popup.show_unregistered.assert_not_called()
        attendance.assert_not_called()


if __name__ == "__main__":
    unittest.main()
