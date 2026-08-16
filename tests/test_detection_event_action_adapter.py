import dataclasses
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from src.core.detection_events import (
    DetectionEventRepository, DetectionEventService, DetectionEventType,
    DetectionEventWriteResult,
)
from src.engine.action_executor import (
    ActionExecutionContext, DetectionEventActionData, ExecutableAction,
)
from src.ui.action_adapters import (
    DetectionEventActionAdapterError, DetectionEventServiceActionAdapter,
)


class ServiceSpy:
    def __init__(self, result=None):
        self.calls = []
        self.result = result or DetectionEventWriteResult(True, True, None, "recorded")

    def observe(self, item):
        self.calls.append(item)
        return self.result


class FailingRepository:
    def create(self, _event):
        raise OSError("controlled repository failure")


def context(person_id=None, state="OBSERVATION_ONLY"):
    return ActionExecutionContext(
        ExecutableAction.LOG_DETECTION_EVENT, person_id, "run", "session", state,
        datetime.now(timezone.utc),
    )


class DetectionEventActionAdapterTests(unittest.TestCase):
    def test_registered_unregistered_incompatible_and_multiple_mapping(self):
        cases = (
            (context("person"), DetectionEventActionData(
                "NOT_EVALUATED", "Temporary", .8, 80, "mock", 1),
             DetectionEventType.REGISTERED_CANDIDATE, "person"),
            (context(), DetectionEventActionData("NO_GALLERY", face_count=1),
             DetectionEventType.UNREGISTERED, None),
            (context(), DetectionEventActionData("INCOMPATIBLE", face_count=1),
             DetectionEventType.INCOMPATIBLE, None),
            (context(state="AMBIGUOUS"), DetectionEventActionData(
                "NOT_EVALUATED", face_count=2), DetectionEventType.MULTIPLE_FACES, None),
        )
        for general, event, expected, person in cases:
            service = ServiceSpy()
            DetectionEventServiceActionAdapter(service).log_proposed_event(general, event)
            self.assertEqual(len(service.calls), 1)
            self.assertEqual(service.calls[0].event_type, expected)
            self.assertEqual(service.calls[0].person_id, person)

    def test_face_count_is_direct_signal_and_no_face_is_rejected(self):
        service = ServiceSpy(); adapter = DetectionEventServiceActionAdapter(service)
        adapter.log_proposed_event(context(state="AMBIGUOUS"),
                                   DetectionEventActionData("NOT_EVALUATED", face_count=1))
        self.assertEqual(service.calls[0].event_type, DetectionEventType.UNREGISTERED)
        with self.assertRaises(DetectionEventActionAdapterError):
            adapter.log_proposed_event(context(),
                                       DetectionEventActionData("NOT_EVALUATED", face_count=0))
        self.assertEqual(len(service.calls), 1)

    def test_not_evaluated_and_cooldown_are_preserved_as_success(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        repository = DetectionEventRepository(Path(temporary.name) / "events.db")
        repository.initialize()
        service = DetectionEventService(repository, registered_cooldown_seconds=60,
                                        monotonic=lambda: 0.0)
        adapter = DetectionEventServiceActionAdapter(service)
        event = DetectionEventActionData("NOT_EVALUATED", "Temporary", .8, 80, "mock", 1)
        adapter.log_proposed_event(context("person"), event)
        adapter.log_proposed_event(context("person"), event)
        self.assertEqual(repository.count(), 1)
        self.assertEqual(repository.list()[0].recognition_state, "NOT_EVALUATED")

    def test_service_failure_is_raised_safely(self):
        service = ServiceSpy(DetectionEventWriteResult(False, False, None, "persistence_error"))
        with self.assertRaisesRegex(DetectionEventActionAdapterError, "service rejected"):
            DetectionEventServiceActionAdapter(service).log_proposed_event(
                context(), DetectionEventActionData("NO_GALLERY"))
        self.assertEqual(len(service.calls), 1)

    def test_real_repository_failure_is_raised_safely(self):
        service = DetectionEventService(FailingRepository())
        with self.assertRaises(DetectionEventActionAdapterError):
            DetectionEventServiceActionAdapter(service).log_proposed_event(
                context("person"), DetectionEventActionData("NOT_EVALUATED"))

    def test_payload_contract_has_only_approved_scalars(self):
        self.assertEqual(
            {field.name for field in dataclasses.fields(DetectionEventActionData)},
            {"recognition_state", "display_name_snapshot", "similarity", "quality_score",
             "camera_id", "face_count", "administrative_status"},
        )
        forbidden = {"cedula", "address", "phone", "email", "thumbnail", "embedding",
                     "template", "ndarray", "model", "gallery"}
        self.assertFalse({field.name for field in dataclasses.fields(
            DetectionEventActionData)} & forbidden)


if __name__ == "__main__":
    unittest.main()
