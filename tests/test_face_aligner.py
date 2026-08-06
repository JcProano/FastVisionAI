from __future__ import annotations

import math
import unittest

import cv2
import numpy as np

from src.camera.frame import Frame
from src.engine.alignment import (
    AlignmentQuality,
    AlignmentStatus,
    FaceAligner,
    LandmarkCorrespondenceError,
)
from src.engine.alignment.face_aligner import CANONICAL_LANDMARKS_112, TEMPLATE_VERSION
from src.engine.contracts.detection import BoundingBox, Detection, InferenceResult
from src.engine.contracts.metrics import InferenceMetrics


class FaceAlignerTests(unittest.TestCase):
    def setUp(self):
        y, x = np.indices((112, 112))
        self.image = np.dstack((x, y, (x + y) % 256)).astype(np.uint8)
        self.frame = Frame.create(
            self.image, sequence_id=7, source_name="synthetic", monotonic_timestamp=1,
            connection_id=2,
        )
        self.detection = Detection(BoundingBox(0.15, 0.15, 0.85, 0.9, True), "face", 0.91)
        self.canonical = tuple(
            (float(x / 112), float(y / 112)) for x, y in CANONICAL_LANDMARKS_112
        )

    def result(self, detections=None, landmark_groups=None, run_id="alignment-run"):
        detections = (self.detection,) if detections is None else detections
        landmark_groups = (self.canonical,) if landmark_groups is None else landmark_groups
        return InferenceResult(
            self.frame, tuple(detections), InferenceMetrics(detection_count=len(detections)),
            1.0, "scheduler:opencv_yunet",
            {"face_detector": {"landmarks": tuple(landmark_groups), "run_id": run_id}},
        )

    def test_correct_alignment_preserves_frame_and_dimensions(self):
        face = FaceAligner().align_result(self.result())[0]
        self.assertIs(face.frame, self.frame)
        self.assertIsNot(face.image, self.frame.image)
        self.assertEqual(face.image.shape, (112, 112, 3))
        self.assertEqual(face.status, AlignmentStatus.ALIGNED)
        self.assertTrue(np.allclose(face.transform_matrix, np.eye(2, 3), atol=1e-6))
        self.assertEqual(TEMPLATE_VERSION, "fva-5pt-112-v1")

    def test_rotation_and_scale_are_corrected(self):
        angle = math.radians(20)
        scale = 0.72
        linear = scale * np.array(((math.cos(angle), -math.sin(angle)),
                                   (math.sin(angle), math.cos(angle))))
        source_pixels = (CANONICAL_LANDMARKS_112 - (56, 56)) @ linear.T + (56, 56)
        landmarks = tuple((float(x / 112), float(y / 112)) for x, y in source_pixels)
        face = FaceAligner().align_result(self.result(landmark_groups=(landmarks,)))[0]
        transformed = cv2.transform(source_pixels[None].astype(np.float64), face.transform_matrix)[0]
        self.assertTrue(np.allclose(transformed, CANONICAL_LANDMARKS_112, atol=1e-6))
        self.assertEqual(face.status, AlignmentStatus.ALIGNED)

    def test_multiple_faces_preserve_original_indices(self):
        detections = (self.detection, self.detection)
        faces = FaceAligner().align_result(
            self.result(detections=detections, landmark_groups=(self.canonical, self.canonical))
        )
        self.assertEqual([face.face_index for face in faces], [0, 1])
        self.assertTrue(all(face.frame is self.frame for face in faces))

    def test_invalid_landmark_count_is_rejected(self):
        face = FaceAligner().align_result(
            self.result(landmark_groups=((self.canonical[0], self.canonical[1]),))
        )[0]
        self.assertEqual(face.status, AlignmentStatus.REJECTED)
        self.assertEqual(face.quality, AlignmentQuality.REJECTED)
        self.assertEqual(face.error, "expected_five_landmarks")

    def test_incorrect_landmark_order_is_rejected(self):
        swapped = list(self.canonical)
        swapped[0], swapped[1] = swapped[1], swapped[0]
        face = FaceAligner().align_result(self.result(landmark_groups=(tuple(swapped),)))[0]
        self.assertEqual(face.status, AlignmentStatus.REJECTED)
        self.assertEqual(face.error, "invalid_landmark_order")

    def test_tiny_face_is_aligned_as_low_quality(self):
        tiny_detection = Detection(BoundingBox(0.49, 0.46, 0.52, 0.52, True), "face", 0.7)
        center = np.array((0.5, 0.5))
        tiny = tuple(tuple(center + (np.array(point) - center) * 0.05) for point in self.canonical)
        face = FaceAligner().align_result(
            self.result(detections=(tiny_detection,), landmark_groups=(tiny,))
        )[0]
        self.assertEqual(face.status, AlignmentStatus.ALIGNED)
        self.assertEqual(face.quality, AlignmentQuality.LOW_QUALITY)

    def test_partially_outside_box_records_visible_ratio(self):
        detection = Detection(BoundingBox(-20, -10, 70, 100, False), "face", 0.8)
        face = FaceAligner().align_result(
            self.result(detections=(detection,), landmark_groups=(self.canonical,))
        )[0]
        self.assertEqual(face.status, AlignmentStatus.ALIGNED)
        self.assertGreater(face.visible_box_ratio, 0)
        self.assertLess(face.visible_box_ratio, 1)

    def test_low_interocular_distance_is_low_quality_not_rejected(self):
        landmarks = ((0.495, 0.35), (0.505, 0.35), (0.5, 0.55), (0.45, 0.75), (0.55, 0.75))
        face = FaceAligner().align_result(self.result(landmark_groups=(landmarks,)))[0]
        self.assertEqual(face.status, AlignmentStatus.ALIGNED)
        self.assertEqual(face.quality, AlignmentQuality.LOW_QUALITY)

    def test_alignment_is_deterministic_and_inverse_is_valid(self):
        first = FaceAligner().align_result(self.result())[0]
        second = FaceAligner().align_result(self.result())[0]
        self.assertTrue(np.array_equal(first.transform_matrix, second.transform_matrix))
        self.assertTrue(np.array_equal(first.image, second.image))
        homogeneous = np.vstack((first.transform_matrix, (0, 0, 1)))
        inverse = np.vstack((first.inverse_transform_matrix, (0, 0, 1)))
        self.assertTrue(np.allclose(inverse @ homogeneous, np.eye(3), atol=1e-8))

    def test_detection_landmark_mismatch_raises_typed_error(self):
        with self.assertRaises(LandmarkCorrespondenceError):
            FaceAligner().align_result(self.result(landmark_groups=()))

    def test_metrics_count_quality_and_rejections(self):
        aligner = FaceAligner()
        invalid = (self.canonical[0],)
        aligner.align_faces(
            (self.detection, self.detection), (self.canonical, invalid), self.frame, "metrics"
        )
        metrics = aligner.metrics()
        self.assertEqual(metrics.faces_received, 2)
        self.assertEqual(metrics.faces_aligned, 1)
        self.assertEqual(metrics.faces_rejected, 1)
        self.assertEqual((metrics.output_width, metrics.output_height), (112, 112))


if __name__ == "__main__":
    unittest.main()
