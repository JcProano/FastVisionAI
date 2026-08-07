from __future__ import annotations

import dataclasses
import time
import unittest

import numpy as np

from src.engine.enrollment import EnrollmentPolicy, EnrollmentService
from src.engine.gallery import FaceGallery, FaceIdentity, FaceMatcher, MatchPolicy
from src.ui.contracts import (
    EnrollmentResultDTO, ErrorDTO, MonitoringDTO, UIErrorCode, UIState, VisualFrameDTO,
)
from src.ui.controller import LocalFaceUIController
from src.ui.enrollment_workflow import LocalEnrollmentWorkflow
from src.ui.form_validation import validate_registration_form
from src.ui.live_session import LiveFaceSession
from src.ui.mock_runtime import MockUIRuntimeAdapter
from src.ui.recognition_session import ExperimentalRecognitionSession


class FailingMatcher(FaceMatcher):
    def match(self, query, gallery):
        raise RuntimeError("controlled")


class OpenFailAdapter(MockUIRuntimeAdapter):
    def open(self):
        return False


def controller(gallery=None, matcher=None, target=3):
    gallery = gallery or FaceGallery()
    matcher = matcher or FaceMatcher(policy=MatchPolicy(False, None))
    service = EnrollmentService(gallery, EnrollmentPolicy(target, target))
    return gallery, LocalFaceUIController(
        ExperimentalRecognitionSession(gallery, matcher),
        LocalEnrollmentWorkflow(gallery, service, target),
    )


def form():
    return validate_registration_form(
        "Temporary", "Person", None, consent_confirmed=True, persist_locally=False,
        id_factory=lambda: "person_ui_test",
    )


def wait_until(predicate, timeout=.8):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return True
        time.sleep(.005)
    return False


class LiveFaceSessionTests(unittest.TestCase):
    def test_monitoring_empty_gallery_visual_backpressure_and_safe_dtos(self):
        gallery, ui = controller()
        adapter = MockUIRuntimeAdapter(delay=.001)
        session = LiveFaceSession(adapter, ui, event_queue_size=3, command_queue_size=2)
        session.start()
        self.assertTrue(wait_until(lambda: adapter.sequence >= 8))
        visual = session.take_latest_visual()
        events = session.drain_events()
        session.close()
        self.assertIsInstance(visual, VisualFrameDTO)
        self.assertLessEqual(session.visual_queue.qsize(), 1)
        self.assertLessEqual(len(events), 3)
        self.assertTrue(any(isinstance(item, MonitoringDTO) and
                            item.message == "Sin candidatos registrados" for item in events))
        for event in events:
            if dataclasses.is_dataclass(event):
                self.assertFalse(any(isinstance(value, np.ndarray)
                                     for value in dataclasses.astuple(event)))

    def test_complete_enrollment_returns_to_experimental_candidate(self):
        gallery, ui = controller(target=3)
        adapter = MockUIRuntimeAdapter(delay=.004)
        session = LiveFaceSession(adapter, ui, event_queue_size=32)
        session.start()
        self.assertTrue(wait_until(lambda: adapter.sequence >= 1))
        self.assertTrue(session.start_enrollment(form()))
        seen = []

        def completed():
            seen.extend(session.drain_events())
            return (any(isinstance(item, EnrollmentResultDTO) for item in seen) and
                    any(isinstance(item, MonitoringDTO) and
                        item.message == "Candidato experimental" for item in seen))

        self.assertTrue(wait_until(completed, 1.5))
        session.close()
        self.assertEqual(len(gallery), 1)
        result = next(item for item in seen if isinstance(item, EnrollmentResultDTO))
        self.assertEqual(result.templates_registered, 3)
        candidate = next(item for item in seen if isinstance(item, MonitoringDTO) and
                         item.message == "Candidato experimental")
        self.assertEqual(candidate.automatic_decision, "NOT_EVALUATED")

    def test_cancel_discards_temporary_samples(self):
        gallery, ui = controller(target=20)
        adapter = MockUIRuntimeAdapter(delay=.02)
        session = LiveFaceSession(adapter, ui)
        session.start(); self.assertTrue(wait_until(lambda: adapter.sequence >= 1))
        session.start_enrollment(form())
        self.assertTrue(wait_until(lambda: ui.enrollment.active))
        session.cancel_enrollment()
        self.assertTrue(wait_until(lambda: not ui.enrollment.active))
        session.close()
        self.assertEqual(len(gallery), 0)

    def test_camera_and_inference_errors_are_safe_and_recovery_continues(self):
        _, ui = controller()
        adapter = MockUIRuntimeAdapter(fail_camera_at={2}, fail_inference_at={4}, delay=.002)
        session = LiveFaceSession(adapter, ui, event_queue_size=32)
        session.start(); self.assertTrue(wait_until(lambda: adapter.sequence >= 7))
        events = session.drain_events(); session.close()
        codes = {item.operation for item in events if isinstance(item, ErrorDTO)}
        self.assertIn(UIErrorCode.CAMERA_ERROR, codes)
        self.assertIn(UIErrorCode.INFERENCE_ERROR, codes)
        self.assertTrue(any(isinstance(item, MonitoringDTO) for item in events))

    def test_open_failure_and_close_during_inference_are_bounded(self):
        _, ui = controller()
        failed = LiveFaceSession(OpenFailAdapter(), ui)
        failed.start(); self.assertTrue(wait_until(lambda: not failed.alive))
        self.assertTrue(any(isinstance(item, ErrorDTO) and
                            item.operation is UIErrorCode.CAMERA_ERROR
                            for item in failed.drain_events()))
        failed.close()

        _, ui2 = controller()
        slow = MockUIRuntimeAdapter(delay=.3)
        session = LiveFaceSession(slow, ui2, close_timeout_seconds=.01)
        session.start(); time.sleep(.02)
        started = time.monotonic(); stopped = session.close(); elapsed = time.monotonic() - started
        self.assertLess(elapsed, .1)
        self.assertFalse(stopped)
        self.assertTrue(wait_until(lambda: not session.alive, .6))
        self.assertTrue(slow.closed)

    def test_matcher_error_multiple_faces_and_nonblocking_command(self):
        gallery = FaceGallery()
        # Compatible template makes the failing matcher path reachable.
        mock = MockUIRuntimeAdapter(delay=.003, multiple_at={2})
        mock.open(); step = mock.process(__import__("src.engine.capture_quality", fromlist=["CapturePose"]).CapturePose.FRONTAL)
        gallery.register_identity(FaceIdentity("existing", "Existing"))
        gallery.add_template("existing", step.guided.embedding)
        matcher = FailingMatcher(policy=MatchPolicy(False, None))
        _, ui = controller(gallery, matcher)
        session = LiveFaceSession(mock, ui, event_queue_size=32)
        session.start()
        started = time.monotonic(); accepted = session.start_enrollment(form())
        self.assertLess(time.monotonic() - started, .02)
        self.assertTrue(accepted)
        self.assertTrue(wait_until(lambda: mock.sequence >= 7))
        events = session.drain_events(); session.close()
        self.assertTrue(any(isinstance(item, MonitoringDTO) and
                            item.state is UIState.MULTIPLE_FACES for item in events))
        self.assertTrue(any(isinstance(item, ErrorDTO) and
                            item.operation is UIErrorCode.MATCHER_ERROR for item in events))


if __name__ == "__main__":
    unittest.main()
