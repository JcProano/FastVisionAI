from __future__ import annotations

import dataclasses
import time
import unittest
from dataclasses import replace
import tempfile
from pathlib import Path

import numpy as np

from src.engine.enrollment import EnrollmentPolicy, EnrollmentService
from src.engine.capture_quality import CapturePlanStep, CapturePose, GuidedCapturePlan, GuidedCaptureState
from src.engine.gallery import FaceGallery, FaceIdentity, FaceMatcher, MatchPolicy
from src.engine.recognition import RecognitionPolicy, RecognitionService
from src.engine.stability import StabilityPolicy, StabilityTracker
from src.ui.contracts import (
    EnrollmentProgressDTO, EnrollmentResultDTO, ErrorDTO, MonitoringDTO,
    UIErrorCode, UIState, VisualFrameDTO,
)
from src.ui.controller import LocalFaceUIController
from src.ui.enrollment_workflow import LocalEnrollmentWorkflow
from src.ui.form_validation import validate_registration_form
from src.ui.live_session import LiveFaceSession, operator_instruction
from src.ui.mock_runtime import MockUIRuntimeAdapter
from src.ui.recognition_session import ExperimentalRecognitionSession
from src.ui.people.controller import PeopleManagerController
from src.ui.identification import (
    IdentificationPopupPolicy, IdentificationPresentationController,
    IdentityPersonDTO,
)
from src.ui.thumbnails import ThumbnailDTO
from src.engine.gallery.persistence import GalleryPersistence


class FailingMatcher(FaceMatcher):
    def match(self, query, gallery):
        raise RuntimeError("controlled")


class CountingRecognitionService(RecognitionService):
    def __init__(self, gallery, matcher, policy):
        super().__init__(gallery, matcher, policy)
        self.calls = 0

    def recognize(self, query, quality_score=None):
        self.calls += 1
        return super().recognize(query, quality_score)


class OpenFailAdapter(MockUIRuntimeAdapter):
    def open(self):
        return False


class IdentityProvider:
    def get_person(self, person_id):
        return IdentityPersonDTO(
            person_id, "Temporary", "Person", "Temporary Person", None,
            status="ACTIVE",
        )

    def get_thumbnail(self, person_id):
        return ThumbnailDTO(person_id, True, 224, 224, "jpeg", b"safe")


class ResetCountingStabilityTracker(StabilityTracker):
    def __init__(self):
        super().__init__(StabilityPolicy(
            minimum_observations=1, minimum_duration_seconds=0,
        ))
        self.reset_count = 0

    def reset(self):
        self.reset_count += 1
        return super().reset()


def controller(gallery=None, matcher=None, target=3, recognition=None):
    gallery = gallery if gallery is not None else FaceGallery()
    matcher = matcher or FaceMatcher(policy=MatchPolicy(False, None))
    recognition = recognition or RecognitionService(
        gallery, matcher, RecognitionPolicy(top_k=matcher.top_k)
    )
    enrollment_service = EnrollmentService(gallery, EnrollmentPolicy(target, target))
    return gallery, LocalFaceUIController(
        ExperimentalRecognitionSession(recognition),
        LocalEnrollmentWorkflow(gallery, enrollment_service, target),
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
    def test_registered_pause_stops_recognition_but_video_worker_continues(self):
        gallery = FaceGallery()
        matcher = FaceMatcher(policy=MatchPolicy(False, None))
        recognition = CountingRecognitionService(
            gallery, matcher, RecognitionPolicy(top_k=matcher.top_k)
        )
        _, ui = controller(gallery, matcher, target=3, recognition=recognition)
        clock = [0.0]
        presentation = IdentificationPresentationController(
            IdentificationPopupPolicy(candidate_stability_frames=1,
                                      registered_pause_seconds=60),
            IdentityProvider(), monotonic=lambda: clock[0],
        )
        popup = presentation.observe(MonitoringDTO(
            UIState.MONITORING, "Candidato experimental", "Temporary Person", .83,
            "deshabilitada / NOT_EVALUATED", True,
            recognition_state="NOT_EVALUATED", candidate_person_id="person",
        ))
        self.assertEqual(popup.person_id, "person")
        stability = ResetCountingStabilityTracker()
        session = LiveFaceSession(
            MockUIRuntimeAdapter(delay=.005), ui, event_queue_size=64,
            identification_presentation=presentation,
            stability_tracker=stability,
        )
        session.start()
        self.assertTrue(wait_until(
            lambda: session.dashboard_telemetry()[0].frames_processed >= 3
        ))
        self.assertEqual(recognition.calls, 0)
        self.assertTrue(session.alive)
        clock[0] = 60
        self.assertTrue(wait_until(lambda: recognition.calls > 0))
        self.assertGreaterEqual(stability.reset_count, 2)
        session.close()

    def test_recognition_is_suspended_during_primary_enrollment_and_reactivated(self):
        gallery = FaceGallery()
        matcher = FaceMatcher(policy=MatchPolicy(False, None))
        recognition = CountingRecognitionService(
            gallery, matcher, RecognitionPolicy(top_k=matcher.top_k)
        )
        _, ui = controller(gallery, matcher, target=20, recognition=recognition)
        session = LiveFaceSession(MockUIRuntimeAdapter(delay=.01), ui, event_queue_size=64)
        session.start()
        self.assertTrue(wait_until(lambda: recognition.calls >= 2))
        session.start_enrollment(form())
        self.assertTrue(wait_until(lambda: ui.enrollment.active))
        calls_during = recognition.calls
        time.sleep(.08)
        self.assertEqual(recognition.calls, calls_during)
        session.cancel_enrollment()
        self.assertTrue(wait_until(lambda: not ui.enrollment.active))
        self.assertTrue(wait_until(lambda: recognition.calls > calls_during))
        session.close()

    def test_recognition_is_suspended_during_additional_enrollment_and_reactivated(self):
        gallery = FaceGallery()
        gallery.register_identity(FaceIdentity("existing", "Existing Person", {
            "first_name": "Existing", "last_name": "Person",
        }))
        gallery.add_template("existing", self._mock_embedding(distinct=True))
        matcher = FaceMatcher(policy=MatchPolicy(False, None))
        recognition = CountingRecognitionService(
            gallery, matcher, RecognitionPolicy(top_k=matcher.top_k)
        )
        _, ui = controller(gallery, matcher, target=20, recognition=recognition)
        root = Path(tempfile.mkdtemp())
        people = PeopleManagerController(
            gallery, ui.enrollment.enrollment, GalleryPersistence(enabled=True),
            root / "gallery.json", root / "gallery.npz",
        )
        session = LiveFaceSession(
            MockUIRuntimeAdapter(delay=.01), ui, people_controller=people, event_queue_size=64
        )
        session.start()
        self.assertTrue(wait_until(lambda: recognition.calls >= 2))
        session.start_additional_enrollment("existing")
        self.assertTrue(wait_until(lambda: people.state.value == "enrolling_more"))
        calls_during = recognition.calls
        time.sleep(.08)
        self.assertEqual(recognition.calls, calls_during)
        session.cancel_enrollment()
        self.assertTrue(wait_until(lambda: people.state.value == "idle"))
        self.assertTrue(wait_until(lambda: recognition.calls > calls_during))
        session.close()

    def test_additional_enrollment_unknown_cancel_and_complete(self):
        gallery = FaceGallery()
        gallery.register_identity(FaceIdentity("existing", "Existing Person", {
            "first_name": "Existing", "last_name": "Person",
        }))
        gallery.add_template("existing", self._mock_embedding(distinct=True))
        _, ui = controller(gallery, target=2)
        root = Path(tempfile.mkdtemp())
        people = PeopleManagerController(
            gallery, ui.enrollment.enrollment, GalleryPersistence(enabled=True),
            root / "gallery.json", root / "gallery.npz",
        )
        adapter = MockUIRuntimeAdapter(delay=.02)
        session = LiveFaceSession(adapter, ui, people_controller=people, event_queue_size=64)
        session.start()
        self.assertTrue(session.start_additional_enrollment("missing"))
        self.assertTrue(wait_until(lambda: people.state.value == "error"))
        self.assertEqual(len(gallery.templates()), 1)

        self.assertTrue(session.start_additional_enrollment("existing"))
        self.assertTrue(wait_until(lambda: people.state.value == "enrolling_more"))
        session.cancel_enrollment()
        self.assertTrue(wait_until(lambda: people.state.value == "idle"))
        self.assertEqual(len(gallery.templates()), 1)

        session.start_additional_enrollment("existing")
        self.assertTrue(wait_until(lambda: len(gallery.templates()) == 3, 1.5))
        self.assertEqual(people.state.value, "idle")
        session.close()

    def _mock_embedding(self, distinct=False):
        adapter = MockUIRuntimeAdapter(delay=0)
        adapter.open()
        embedding = adapter.process(CapturePose.FRONTAL).guided.embedding
        if distinct:
            vector = np.zeros(embedding.dimension, np.float32); vector[100] = 1
            embedding = replace(embedding, embedding=vector)
        return embedding

    def test_operator_pose_instructions_respect_mirrored_perspective(self):
        left = CapturePlanStep("left", CapturePose.SLIGHT_LEFT,
                               "Gire ligeramente a la izquierda")
        right = CapturePlanStep("right", CapturePose.SLIGHT_RIGHT,
                                "Gire ligeramente a la derecha")
        frontal = CapturePlanStep("front", CapturePose.FRONTAL, "Mire al frente")
        self.assertEqual(operator_instruction(left, False), "Gire ligeramente a la izquierda")
        self.assertEqual(operator_instruction(right, False), "Gire ligeramente a la derecha")
        self.assertEqual(operator_instruction(left, True), "Gire ligeramente a la derecha")
        self.assertEqual(operator_instruction(right, True), "Gire ligeramente a la izquierda")
        self.assertEqual(operator_instruction(frontal, True), "Mire al frente")

    def test_mirrored_presentation_preserves_guided_plan_logical_order(self):
        plan = GuidedCapturePlan(4)
        logical = []
        messages = []
        while not plan.completed:
            logical.append(plan.current.requested_pose)
            messages.append(operator_instruction(plan.current, True))
            plan.accept()
        self.assertEqual(logical, [
            CapturePose.FRONTAL, CapturePose.SLIGHT_LEFT,
            CapturePose.SLIGHT_RIGHT, CapturePose.FRONTAL,
        ])
        self.assertEqual(messages, [
            "Mire al frente", "Gire ligeramente a la derecha",
            "Gire ligeramente a la izquierda", "Mire al frente con expresión neutra",
        ])

    def test_enrollment_progress_message_uses_operator_perspective(self):
        _, ui = controller(target=3)
        adapter = MockUIRuntimeAdapter(delay=.02)
        session = LiveFaceSession(adapter, ui, event_queue_size=32, mirrored_source=True)
        session.start(); session.start_enrollment(form())
        seen = []

        def has_mirrored_left_step():
            seen.extend(session.drain_events())
            return any(isinstance(item, EnrollmentProgressDTO) and
                       item.accepted_samples == 1 and
                       item.instruction == "Gire ligeramente a la derecha"
                       for item in seen)

        self.assertTrue(wait_until(has_mirrored_left_step))
        session.cancel_enrollment(); session.close()

    def test_enrollment_starts_immediately_before_any_valid_face(self):
        class NoFaceThenValidAdapter(MockUIRuntimeAdapter):
            def process(self, requested_pose):
                step = super().process(requested_pose)
                if self.sequence <= 2:
                    rejected = replace(
                        step.guided,
                        primary_state=GuidedCaptureState.NO_FACE,
                        reasons=(GuidedCaptureState.NO_FACE,),
                        accepted=False,
                        visual_quality_passed=False,
                        temporal_check_passed=False,
                        diversity_check_passed=False,
                        face_index=None,
                        embedding=None,
                    )
                    return replace(step, face_count=0, guided=rejected)
                return step

        gallery, ui = controller(target=3)
        adapter = NoFaceThenValidAdapter(delay=.05)
        session = LiveFaceSession(adapter, ui, event_queue_size=32)
        session.start()
        self.assertTrue(session.start_enrollment(form()))
        seen = []

        def started():
            seen.extend(session.drain_events())
            return any(isinstance(item, EnrollmentProgressDTO) and
                       item.accepted_samples == 0 and item.target_samples == 3 and
                       item.instruction == "Mire al frente" for item in seen)

        self.assertTrue(wait_until(started))
        def has_no_face_progress():
            seen.extend(session.drain_events())
            return any(
                isinstance(item, EnrollmentProgressDTO)
                and "no_face" in item.current_reasons
                and item.accepted_samples == 0
                for item in seen
            )

        self.assertTrue(wait_until(has_no_face_progress))
        self.assertEqual(ui.state, UIState.ENROLLING)
        self.assertTrue(ui.enrollment.active)
        session.cancel_enrollment()
        self.assertTrue(wait_until(lambda: not ui.enrollment.active))
        session.close()
        self.assertEqual(len(gallery), 0)

    def test_multiple_and_invalid_faces_remain_enrolling_then_valid_face_advances(self):
        class RecoveringAdapter(MockUIRuntimeAdapter):
            def open(self):
                time.sleep(.05)
                return super().open()

            def process(self, requested_pose):
                step = super().process(requested_pose)
                if self.sequence == 2:
                    rejected = replace(
                        step.guided,
                        primary_state=GuidedCaptureState.BLURRY,
                        reasons=(GuidedCaptureState.BLURRY,),
                        accepted=False,
                        visual_quality_passed=False,
                        temporal_check_passed=False,
                        diversity_check_passed=False,
                        embedding=None,
                    )
                    return replace(step, guided=rejected)
                return step

        gallery, ui = controller(target=5)
        adapter = RecoveringAdapter(delay=.02, multiple_at={1})
        session = LiveFaceSession(adapter, ui, event_queue_size=64)
        session.start(); session.start_enrollment(form())
        seen = []

        def progressed_after_rejections():
            seen.extend(session.drain_events())
            rejected = [item for item in seen if isinstance(item, EnrollmentProgressDTO)
                        and item.accepted_samples == 0 and item.current_reasons]
            progressed = any(isinstance(item, EnrollmentProgressDTO) and
                             item.accepted_samples >= 1 for item in seen)
            return len(rejected) >= 2 and progressed

        self.assertTrue(wait_until(progressed_after_rejections, 1.2))
        rejected_reasons = {reason for item in seen if isinstance(item, EnrollmentProgressDTO)
                            for reason in item.current_reasons}
        self.assertIn("multiple_faces", rejected_reasons)
        self.assertIn("blurry", rejected_reasons)
        self.assertEqual(ui.state, UIState.ENROLLING)
        self.assertTrue(ui.enrollment.active)
        session.cancel_enrollment(); self.assertTrue(wait_until(lambda: not ui.enrollment.active))
        session.close(); self.assertEqual(len(gallery), 0)

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
