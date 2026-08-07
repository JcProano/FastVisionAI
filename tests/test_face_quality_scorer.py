from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path

from src.engine.alignment import AlignmentStatus
from src.engine.capture_quality import CapturePose, GuidedCaptureState, GuidedQualityMetrics
from src.engine.face_quality import FaceQualityScorer, QualityBand, load_face_quality_profile
from src.engine.face_quality.contracts import FaceQualityWeights


class FaceQualityScorerTests(unittest.TestCase):
    def setUp(self):
        self.profile = load_face_quality_profile(Path("config/face_quality.dev.json"))
        self.scorer = FaceQualityScorer(self.profile)

    def metrics(self, **changes):
        values = dict(
            detection_confidence=.95, relative_face_size=.20,
            normalized_interocular_distance=.25, visible_box_ratio=1.0,
            center_offset_x=0.0, center_offset_y=0.0, mean_illumination=130,
            contrast=60, blur_variance=250, eye_nose_yaw_ratio=0,
            mouth_nose_yaw_ratio=0, checks_passed=10, checks_total=10,
            quality_score=1.0,
        )
        values.update(changes)
        return GuidedQualityMetrics(**values)

    def score(self, metrics=None, reasons=(GuidedCaptureState.ACCEPTED,),
              requested=CapturePose.FRONTAL, estimated=CapturePose.FRONTAL,
              alignment=AlignmentStatus.ALIGNED):
        return self.scorer.score(
            metrics or self.metrics(), requested, estimated, reasons, alignment,
            (metrics or self.metrics()).detection_confidence, "run", 3,
        )

    def test_score_is_deterministic_and_all_components_are_bounded(self):
        first = self.score(); second = self.score()
        self.assertEqual(first, second)
        for name, value in first.__dict__.items() if hasattr(first, "__dict__") else ():
            if name.endswith("score"):
                self.assertGreaterEqual(value, 0); self.assertLessEqual(value, 100)
        component_values = (
            first.total_score, first.detection_score, first.size_score,
            first.interocular_score, first.visibility_score, first.centering_score,
            first.sharpness_score, first.illumination_score, first.contrast_score,
            first.pose_score,
        )
        self.assertTrue(all(0 <= value <= 100 for value in component_values))
        self.assertAlmostEqual(first.total_score, 100.0)

    def test_sharp_centered_visible_and_well_lit_score_higher(self):
        baseline = self.score()
        blurry = self.score(self.metrics(blur_variance=0), (GuidedCaptureState.BLURRY,))
        dark = self.score(self.metrics(mean_illumination=0), (GuidedCaptureState.TOO_DARK,))
        bright = self.score(self.metrics(mean_illumination=255), (GuidedCaptureState.TOO_BRIGHT,))
        off_center = self.score(self.metrics(center_offset_x=.5, center_offset_y=.5),
                                (GuidedCaptureState.FACE_OFF_CENTER,))
        partial = self.score(self.metrics(visible_box_ratio=.5),
                             (GuidedCaptureState.PARTIALLY_VISIBLE,))
        self.assertGreater(baseline.sharpness_score, blurry.sharpness_score)
        self.assertGreater(baseline.illumination_score, dark.illumination_score)
        self.assertGreater(baseline.illumination_score, bright.illumination_score)
        self.assertGreater(baseline.centering_score, off_center.centering_score)
        self.assertGreater(baseline.visibility_score, partial.visibility_score)
        self.assertTrue(all(baseline.total_score > item.total_score
                            for item in (blurry, dark, bright, off_center, partial)))

    def test_pose_correct_incorrect_and_unknown(self):
        correct = self.score()
        incorrect = self.score(reasons=(GuidedCaptureState.POSE_NOT_REQUESTED,),
                               estimated=CapturePose.SLIGHT_LEFT)
        unknown = self.score(reasons=(GuidedCaptureState.POSE_NOT_REQUESTED,),
                             estimated=CapturePose.UNKNOWN)
        self.assertGreater(correct.pose_score, incorrect.pose_score)
        self.assertGreater(incorrect.pose_score, unknown.pose_score)

    def test_structural_failure_is_invalid_but_non_structural_keeps_partial_score(self):
        invalid = self.score(GuidedQualityMetrics(), (GuidedCaptureState.NO_FACE,),
                             alignment=None)
        partial = self.score(self.metrics(blur_variance=0), (GuidedCaptureState.BLURRY,))
        self.assertEqual(invalid.total_score, 0)
        self.assertEqual(invalid.quality_band, QualityBand.INVALID)
        self.assertGreater(partial.total_score, 0)
        self.assertNotEqual(partial.quality_band, QualityBand.INVALID)

    def test_invalid_weight_sum_is_rejected_strictly(self):
        bad_weights = replace(self.profile.weights, detection=.1200000001)
        with self.assertRaisesRegex(ValueError, "sum"):
            replace(self.profile, weights=bad_weights)

    def test_bands_profile_and_version(self):
        excellent = self.score()
        poor = self.score(self.metrics(
            detection_confidence=.5, relative_face_size=.03,
            normalized_interocular_distance=.04, visible_box_ratio=.7,
            center_offset_x=.5, mean_illumination=20, contrast=8, blur_variance=20,
        ), (GuidedCaptureState.BLURRY,))
        self.assertEqual(excellent.quality_band, QualityBand.EXCELLENT)
        self.assertEqual(poor.quality_band, QualityBand.POOR)
        self.assertEqual(excellent.profile_name, "face_quality_development")
        self.assertEqual(excellent.profile_version, "1.0.0")

    def test_configured_band_boundaries(self):
        profile = replace(self.profile, weights=FaceQualityWeights(1, 0, 0, 0, 0, 0, 0, 0, 0),
                          critical_penalties={})
        scorer = FaceQualityScorer(profile)
        expected = ((90, QualityBand.EXCELLENT), (75, QualityBand.GOOD),
                    (55, QualityBand.ACCEPTABLE), (25, QualityBand.POOR))
        for target, band in expected:
            confidence = profile.detection.minimum + target / 100 * (
                profile.detection.full_score - profile.detection.minimum
            )
            score = scorer.score(
                self.metrics(detection_confidence=confidence), CapturePose.FRONTAL,
                CapturePose.FRONTAL, (), AlignmentStatus.ALIGNED, confidence, "run", 0,
            )
            self.assertAlmostEqual(score.total_score, target)
            self.assertEqual(score.quality_band, band)

    def test_safe_output_has_no_embedding_or_image(self):
        rendered = repr(self.score()).lower()
        self.assertNotIn("embedding", rendered)
        self.assertNotIn("image", rendered)


if __name__ == "__main__": unittest.main()
