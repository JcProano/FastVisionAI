import queue
import unittest
from datetime import datetime, timezone

from src.core.application_events import (
    ApplicationEvent, ApplicationEventBus, DetectionEventStoredEvent,
    MonitoringUpdatedEvent, PopupRequestedEvent,
)
from src.core.detection_events import DetectionEventWriteResult
from src.engine.action_executor import (
    ActionExecutionContext, DetectionEventActionData, ExecutableAction, PopupActionData,
)
from src.ui.action_adapters import (
    DetectionEventServiceActionAdapter, IdentificationPopupActionAdapter,
)
from src.ui.contracts import MonitoringDTO, UIState
from src.ui.identification import (
    IdentificationPopupPolicy, IdentificationPresentationController, IdentityPersonDTO,
)
from src.ui.live_session import LiveFaceSession
from src.ui.thumbnails import ThumbnailDTO


class Provider:
    def get_person(self, person_id):
        return IdentityPersonDTO(person_id, "Temporary", "Person", "Temporary Person", None)
    def get_thumbnail(self, person_id):
        return ThumbnailDTO(person_id, False, 0, 0, "jpeg", None)


class EventService:
    def __init__(self, *, success=True, recorded=True):
        self.success = success; self.recorded = recorded
    def observe(self, _item):
        return DetectionEventWriteResult(self.success, self.recorded, None, "safe")


def context(action, person_id=None):
    return ActionExecutionContext(
        action, person_id, "run", "session", "NOT_EVALUATED", datetime.now(timezone.utc),
    )


class ApplicationEventIntegrationTests(unittest.TestCase):
    def test_live_queue_remains_primary_and_bus_receives_parallel_projection(self):
        bus = ApplicationEventBus(); published = []
        bus.subscribe(ApplicationEvent, published.append)
        live = LiveFaceSession.__new__(LiveFaceSession)
        live.event_queue = queue.Queue(maxsize=2)
        live._application_events = bus; live._session_id = "session"
        dto = MonitoringDTO(UIState.MONITORING, "safe", None, None, "off", True)
        live._event(dto)
        self.assertIs(live.event_queue.get_nowait(), dto)
        self.assertEqual(len(published), 1)
        self.assertIsInstance(published[0], MonitoringUpdatedEvent)
        self.assertIs(published[0].monitoring, dto)

    def test_no_bus_keeps_existing_queue_behavior(self):
        live = LiveFaceSession.__new__(LiveFaceSession)
        live.event_queue = queue.Queue(maxsize=1); live._application_events = None
        live._session_id = "session"
        dto = MonitoringDTO(UIState.MONITORING, "safe", None, None, "off", True)
        live._event(dto)
        self.assertIs(live.event_queue.get_nowait(), dto)

    def test_popup_adapter_publishes_once_even_when_suppressed(self):
        bus = ApplicationEventBus(); events = []
        bus.subscribe(PopupRequestedEvent, events.append)
        controller = IdentificationPresentationController(
            IdentificationPopupPolicy(True, 10, 10, 2, 60), Provider(),
            monotonic=lambda: 0.0,
        )
        adapter = IdentificationPopupActionAdapter(
            controller, application_event_bus=bus,
        )
        adapter.show_registered(
            context(ExecutableAction.SHOW_REGISTERED_POPUP, "person"),
            PopupActionData("NOT_EVALUATED", .8),
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].presentation_state, "SUPPRESSED")
        self.assertEqual(adapter.drain(), ())

    def test_detection_adapter_publishes_only_after_service_success(self):
        for success, recorded, expected in ((True, True, 1), (True, False, 1), (False, False, 0)):
            with self.subTest(success=success, recorded=recorded):
                bus = ApplicationEventBus(); events = []
                bus.subscribe(DetectionEventStoredEvent, events.append)
                adapter = DetectionEventServiceActionAdapter(
                    EventService(success=success, recorded=recorded), bus,
                )
                if success:
                    adapter.log_proposed_event(
                        context(ExecutableAction.LOG_DETECTION_EVENT),
                        DetectionEventActionData("NO_GALLERY", camera_id="mock"),
                    )
                else:
                    with self.assertRaises(Exception):
                        adapter.log_proposed_event(
                            context(ExecutableAction.LOG_DETECTION_EVENT),
                            DetectionEventActionData("NO_GALLERY", camera_id="mock"),
                        )
                self.assertEqual(len(events), expected)
                if events: self.assertEqual(events[0].recorded, recorded)


if __name__ == "__main__": unittest.main()
