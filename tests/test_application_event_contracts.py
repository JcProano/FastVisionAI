import dataclasses
import unittest
from datetime import datetime, timezone

from src.core.application_events import (
    ActionExecutionUpdatedEvent, ApplicationEvent, ApplicationEventValidationError,
    DecisionUpdatedEvent, DetectionEventStoredEvent, EnrollmentCancelledEvent,
    EnrollmentFinishedEvent, EnrollmentStartedEvent, IdentificationPolicyUpdatedEvent,
    MonitoringUpdatedEvent, PopupDismissedEvent, PopupRequestedEvent,
    StabilityUpdatedEvent,
)
from src.ui.contracts import (
    ActionExecutorDTO, DecisionOrchestratorDTO, IdentificationPolicyDTO,
    MonitoringDTO, StabilityDTO, UIState,
)


class ApplicationEventContractTests(unittest.TestCase):
    def test_base_is_immutable_identified_and_timezone_aware(self):
        event = ApplicationEvent(source="test")
        self.assertTrue(event.event_id)
        self.assertIsNotNone(event.timestamp.tzinfo)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            event.source = "changed"
        with self.assertRaises(ApplicationEventValidationError):
            ApplicationEvent(source="", timestamp=datetime.now())

    def test_all_approved_types_are_constructible_with_safe_payloads(self):
        monitoring = MonitoringDTO(UIState.MONITORING, "ok", None, None, "off", True)
        stability = StabilityDTO("OBSERVING", None, 1, 3, 0.1, 1.0, None, None, "safe")
        policy = IdentificationPolicyDTO(
            "NOT_EVALUATED", False, False, None, (), None, None, "OBSERVING",
            None, "p", "1", False,
        )
        decision = DecisionOrchestratorDTO(
            "NOT_EVALUATED", False, None, (), (), (), False, "p", "1",
        )
        execution = ActionExecutorDTO(
            "NOT_EVALUATED", False, (), (), (), (), (), False, "p", "1",
        )
        events = (
            MonitoringUpdatedEvent(source="test", monitoring=monitoring),
            StabilityUpdatedEvent(source="test", stability=stability),
            IdentificationPolicyUpdatedEvent(source="test", policy=policy),
            DecisionUpdatedEvent(source="test", decision=decision),
            ActionExecutionUpdatedEvent(source="test", execution=execution),
            EnrollmentStartedEvent(source="test", person_id=None, state="ENROLLING", message="safe"),
            EnrollmentFinishedEvent(source="test", person_id="uuid", state="ENROLLED", message="safe"),
            EnrollmentCancelledEvent(source="test", person_id=None, state="CANCELLED", message="safe"),
            DetectionEventStoredEvent(source="test", detection_event_id=None, person_id=None,
                                      detection_event_type="unregistered", camera_id="0", recorded=False),
            PopupRequestedEvent(source="test", popup_action="show", person_id=None,
                                presentation_state="suppressed", reason="cooldown"),
            PopupDismissedEvent(source="test", popup_type="unregistered", reason="timeout"),
        )
        self.assertEqual(len({event.event_type for event in events}), len(events))
        forbidden = {"embedding", "template", "image", "model", "cedula", "address",
                     "phone", "email", "notes"}
        for event in events:
            self.assertTrue(forbidden.isdisjoint(field.name for field in dataclasses.fields(event)))


if __name__ == "__main__": unittest.main()
