from __future__ import annotations

import unittest
from datetime import datetime, timezone

import numpy as np

from src.camera.frame import Frame
from src.engine.alignment import AlignedFace, AlignmentQuality, AlignmentStatus
from src.engine.capture_quality import (
    CapturePose, FaceCaptureQualityEvaluator, GuidedCapturePolicy, GuidedCaptureState,
)
from src.engine.contracts.detection import BoundingBox, Detection
from src.engine.embedding.contracts import FaceEmbedding


class FaceCaptureQualityTests(unittest.TestCase):
    def setUp(self):
        self.policy = GuidedCapturePolicy(
            .7, .05, .08, .9, .2, .2, 10, 30, 225, 10,
            .08, .12, .40, .10, 1.0, .98,
        )

    def frame(self, sequence=1, timestamp=1.0, image=None):
        if image is None:
            tile = np.indices((112, 112)).sum(axis=0) % 2
            image = np.repeat((tile * 180 + 40).astype(np.uint8)[..., None], 3, axis=2)
        return Frame(image, sequence, "mock", datetime.now(timezone.utc), timestamp,
                     image.shape[1], image.shape[0], 1)

    def face(self, *, frame=None, confidence=.9, size=.2, iod=.2, visible=1.0,
             box=(.25, .2, .75, .8), landmarks=None, status=AlignmentStatus.ALIGNED):
        frame = frame or self.frame()
        landmarks = landmarks or ((.35, .4), (.65, .4), (.5, .52), (.4, .68), (.6, .68))
        return AlignedFace(
            frame, frame.image if status is AlignmentStatus.ALIGNED else None,
            BoundingBox(*box, True), tuple(landmarks), np.eye(2, 3), np.eye(2, 3),
            0, confidence, "run", status,
            AlignmentQuality.VALID if status is AlignmentStatus.ALIGNED else AlignmentQuality.REJECTED,
            None, 1.0, iod, size, visible,
        )

    def detection(self, confidence=.9):
        return Detection(BoundingBox(.25, .2, .75, .8, True), "face", confidence, 0)

    def embedding(self, face, vector=(1., 0.)):
        value = np.asarray(vector, dtype=np.float32); value /= np.linalg.norm(value)
        return FaceEmbedding(face.frame, "run", face.face_index, value, 2, 1.0,
                             AlignmentQuality.VALID, 1.0, "mock", "arc", "v1", "sha")

    def test_zero_multiple_and_alignment_failure(self):
        evaluator = FaceCaptureQualityEvaluator(self.policy)
        provider = lambda face: self.embedding(face)
        zero = evaluator.evaluate((), (), CapturePose.FRONTAL, "run", 1, provider)
        many = evaluator.evaluate((self.detection(), self.detection()), (), CapturePose.FRONTAL,
                                  "run", 2, provider)
        failed = evaluator.evaluate((self.detection(),),
                                    (self.face(status=AlignmentStatus.REJECTED),),
                                    CapturePose.FRONTAL, "run", 3, provider)
        self.assertEqual(zero.primary_state, GuidedCaptureState.NO_FACE)
        self.assertEqual(many.primary_state, GuidedCaptureState.MULTIPLE_FACES)
        self.assertEqual(failed.primary_state, GuidedCaptureState.ALIGNMENT_FAILED)

    def test_multiple_visual_reasons_have_complete_deterministic_order(self):
        dark = np.zeros((112, 112, 3), dtype=np.uint8)
        face = self.face(frame=self.frame(image=dark), confidence=.1, size=.01, iod=.01,
                         visible=.5, box=(0, 0, .2, .2))
        result = FaceCaptureQualityEvaluator(self.policy).evaluate(
            (self.detection(),), (face,), CapturePose.SLIGHT_LEFT, "run", 1,
            lambda value: self.embedding(value),
        )
        self.assertEqual(result.primary_state, GuidedCaptureState.LOW_DETECTION_CONFIDENCE)
        self.assertEqual(result.reasons, (
            GuidedCaptureState.LOW_DETECTION_CONFIDENCE,
            GuidedCaptureState.FACE_TOO_SMALL,
            GuidedCaptureState.LOW_INTEROCULAR_DISTANCE,
            GuidedCaptureState.PARTIALLY_VISIBLE,
            GuidedCaptureState.FACE_OFF_CENTER,
            GuidedCaptureState.TOO_DARK,
            GuidedCaptureState.LOW_CONTRAST,
            GuidedCaptureState.BLURRY,
            GuidedCaptureState.POSE_NOT_REQUESTED,
        ))
        self.assertFalse(result.visual_quality_passed)
        self.assertIsNone(result.embedding)

    def test_each_image_and_geometry_gate(self):
        cases = (
            (dict(size=.01), GuidedCaptureState.FACE_TOO_SMALL),
            (dict(iod=.01), GuidedCaptureState.LOW_INTEROCULAR_DISTANCE),
            (dict(visible=.5), GuidedCaptureState.PARTIALLY_VISIBLE),
            (dict(box=(0, 0, .2, .2)), GuidedCaptureState.FACE_OFF_CENTER),
        )
        for changes, reason in cases:
            with self.subTest(reason=reason):
                result = FaceCaptureQualityEvaluator(self.policy).evaluate(
                    (self.detection(),), (self.face(**changes),), CapturePose.FRONTAL,
                    "run", 1, lambda value: self.embedding(value),
                )
                self.assertIn(reason, result.reasons)
        for level, reason in ((0, GuidedCaptureState.TOO_DARK),
                              (255, GuidedCaptureState.TOO_BRIGHT),
                              (128, GuidedCaptureState.LOW_CONTRAST)):
            image = np.full((112, 112, 3), level, dtype=np.uint8)
            result = FaceCaptureQualityEvaluator(self.policy).evaluate(
                (self.detection(),), (self.face(frame=self.frame(image=image)),),
                CapturePose.FRONTAL, "run", 1, lambda value: self.embedding(value),
            )
            self.assertIn(reason, result.reasons)
            self.assertIn(GuidedCaptureState.BLURRY, result.reasons)

    def test_pose_uses_eyes_nose_and_mouth_and_ambiguous_is_unknown(self):
        # Eyes place the nose to image-right while mouth geometry places it left.
        ambiguous = ((.35, .4), (.65, .4), (.61, .52), (.65, .68), (.85, .68))
        result = FaceCaptureQualityEvaluator(self.policy).evaluate(
            (self.detection(),), (self.face(landmarks=ambiguous),), CapturePose.FRONTAL,
            "run", 1, lambda value: self.embedding(value),
        )
        self.assertEqual(result.estimated_pose, CapturePose.UNKNOWN)
        self.assertIn(GuidedCaptureState.POSE_NOT_REQUESTED, result.reasons)

        for nose_x, expected in ((.56, CapturePose.SLIGHT_RIGHT),
                                 (.44, CapturePose.SLIGHT_LEFT)):
            landmarks = ((.35, .4), (.65, .4), (nose_x, .52),
                         (.4, .68), (.6, .68))
            classified = FaceCaptureQualityEvaluator(self.policy).evaluate(
                (self.detection(),), (self.face(landmarks=landmarks),), expected,
                "run", 1, lambda value: self.embedding(value),
            )
            self.assertEqual(classified.estimated_pose, expected)
            self.assertTrue(classified.accepted)

    def test_same_frame_is_accepted_only_once_and_metrics_are_separate(self):
        evaluator = FaceCaptureQualityEvaluator(self.policy)
        face = self.face()
        first = evaluator.evaluate((self.detection(),), (face,), CapturePose.FRONTAL,
                                   "run", 1, lambda value: self.embedding(value))
        second = evaluator.evaluate((self.detection(),), (face,), CapturePose.FRONTAL,
                                    "run", 99, lambda value: self.embedding(value, (0, 1)))
        self.assertTrue(first.accepted)
        self.assertEqual(second.primary_state, GuidedCaptureState.TOO_SOON)
        metrics = evaluator.metrics()
        self.assertEqual(metrics.visually_valid_candidates, 2)
        self.assertEqual(metrics.temporal_rejections, 1)
        self.assertEqual(metrics.embeddings_calculated, 1)
        self.assertEqual(metrics.samples_accepted, 1)

    def test_tentative_acceptance_can_be_rejected_and_best_restored_for_stability(self):
        evaluator = FaceCaptureQualityEvaluator(self.policy)
        face = self.face(frame=self.frame(sequence=1, timestamp=1))
        result = evaluator.evaluate(
            (self.detection(),), (face,), CapturePose.FRONTAL, "run", 1,
            lambda value: self.embedding(value),
        )
        self.assertTrue(evaluator.reject_last_accepted(result))
        self.assertEqual(evaluator.metrics().samples_accepted, 0)
        self.assertTrue(evaluator.restore_accepted(result))
        self.assertEqual(evaluator.metrics().samples_accepted, 1)

    def test_same_timestamp_with_different_sequence_is_not_accepted_twice(self):
        evaluator = FaceCaptureQualityEvaluator(self.policy)
        first = self.face(frame=self.frame(sequence=1, timestamp=1))
        second = self.face(frame=self.frame(sequence=2, timestamp=1))
        evaluator.evaluate((self.detection(),), (first,), CapturePose.FRONTAL,
                           "run", 1, lambda value: self.embedding(value))
        result = evaluator.evaluate((self.detection(),), (second,), CapturePose.FRONTAL,
                                    "run", 3, lambda value: self.embedding(value, (0, 1)))
        self.assertEqual(result.primary_state, GuidedCaptureState.TOO_SOON)

    def test_same_sequence_with_different_timestamp_is_not_accepted_twice(self):
        evaluator = FaceCaptureQualityEvaluator(self.policy)
        first = self.face(frame=self.frame(sequence=7, timestamp=1))
        second = self.face(frame=self.frame(sequence=7, timestamp=3))
        evaluator.evaluate((self.detection(),), (first,), CapturePose.FRONTAL,
                           "run", 1, lambda value: self.embedding(value))
        result = evaluator.evaluate((self.detection(),), (second,), CapturePose.FRONTAL,
                                    "run", 3, lambda value: self.embedding(value, (0, 1)))
        self.assertEqual(result.primary_state, GuidedCaptureState.TOO_SOON)

    def test_embedding_failure_is_typed_and_not_accepted(self):
        evaluator = FaceCaptureQualityEvaluator(self.policy)
        result = evaluator.evaluate(
            (self.detection(),), (self.face(),), CapturePose.FRONTAL, "run", 1,
            lambda _face: (_ for _ in ()).throw(RuntimeError("controlled")),
        )
        self.assertEqual(result.primary_state, GuidedCaptureState.EMBEDDING_FAILED)
        self.assertTrue(result.visual_quality_passed)
        self.assertTrue(result.temporal_check_passed)
        self.assertFalse(result.accepted)
        self.assertIsNone(result.embedding)

    def test_visual_valid_but_near_duplicate(self):
        evaluator = FaceCaptureQualityEvaluator(self.policy)
        first_face = self.face(frame=self.frame(sequence=1, timestamp=1))
        second_face = self.face(frame=self.frame(sequence=2, timestamp=3))
        evaluator.evaluate((self.detection(),), (first_face,), CapturePose.FRONTAL,
                           "run", 1, lambda value: self.embedding(value))
        result = evaluator.evaluate((self.detection(),), (second_face,), CapturePose.FRONTAL,
                                    "run", 3, lambda value: self.embedding(value))
        self.assertEqual(result.primary_state, GuidedCaptureState.NEAR_DUPLICATE)
        self.assertTrue(result.visual_quality_passed)
        self.assertTrue(result.temporal_check_passed)
        self.assertFalse(result.diversity_check_passed)
        self.assertIsNone(result.embedding)
        metrics = evaluator.metrics()
        self.assertEqual(metrics.embeddings_calculated, 2)
        self.assertEqual(metrics.near_duplicate_rejections, 1)


if __name__ == "__main__": unittest.main()
