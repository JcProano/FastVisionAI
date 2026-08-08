from __future__ import annotations

import unittest
from dataclasses import asdict
from datetime import datetime, timezone

from src.engine.capture_quality import (
    CapturePose, GuidedCaptureResult, GuidedCaptureState, GuidedQualityMetrics,
    GuidedProfileDiagnosticCollector,
)
from src.validation.guided_face_capture import load_guided_profile
from pathlib import Path


class GuidedProfileDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        profile = load_guided_profile(Path("config/guided_capture.dev.json"))
        self.collector = GuidedProfileDiagnosticCollector(
            profile.policy, profile.profile_name, profile.profile_version
        )

    def result(self, *, accepted=False, visual=False, reason=GuidedCaptureState.FACE_TOO_SMALL,
               requested=CapturePose.FRONTAL, estimated=CapturePose.FRONTAL,
               interocular=.05, confidence=.8):
        metrics = GuidedQualityMetrics(
            confidence, .09, interocular, .96, .1, .1, 120, 30, 100,
            0.0, 0.0, 7, 10, .7,
        )
        reasons = (GuidedCaptureState.ACCEPTED,) if accepted else (reason,)
        return GuidedCaptureResult(
            reasons[0], reasons, accepted, visual, visual, accepted, metrics,
            requested, estimated, 0, "safe-run", datetime.now(timezone.utc), None, None,
        )

    def test_distributions_are_separated_and_include_profile_limits(self):
        self.collector.record(self.result(accepted=True, visual=True, interocular=.12), 1)
        self.collector.record(self.result(visual=True, reason=GuidedCaptureState.TOO_SOON,
                                          interocular=.11), 1)
        self.collector.record(self.result(interocular=.05,
                                          reason=GuidedCaptureState.LOW_INTEROCULAR_DISTANCE), 1)
        report = self.collector.report()
        self.assertEqual(report.frames_evaluated, 3)
        self.assertEqual(report.accepted_frames, 1)
        self.assertEqual(report.visually_valid_frames, 2)
        self.assertEqual(report.rejected_frames, 2)
        interocular = next(item for item in report.metrics
                           if item.metric == "interocular_distance")
        self.assertEqual(interocular.accepted.count, 1)
        self.assertEqual(interocular.visually_valid.count, 2)
        self.assertEqual(interocular.rejected.count, 2)
        self.assertEqual(interocular.current_limit, {"minimum": .10})
        self.assertEqual(interocular.rejected.percentiles[2][0], 50.0)
        self.assertEqual(report.interocular.available_frames, 3)
        self.assertEqual(report.interocular.below_limit_frames, 1)

    def test_pose_confusion_unknown_match_and_limits(self):
        self.collector.record(self.result(accepted=True, visual=True), 1)
        self.collector.record(self.result(requested=CapturePose.SLIGHT_LEFT,
                                          estimated=CapturePose.UNKNOWN), 1)
        report = self.collector.report()
        self.assertEqual(report.pose.evaluable_frames, 2)
        self.assertEqual(report.pose.unknown_percentage, 50.0)
        self.assertEqual(report.pose.match_percentage, 50.0)
        self.assertIn("frontal_max_yaw_ratio", report.pose.current_limits)
        frontal_row = dict(report.pose.confusion_matrix)["frontal"]
        self.assertEqual(dict(frontal_row)["frontal"], 1)

    def test_face_count_histogram_and_ranked_rejection_controls(self):
        self.collector.record(self.result(reason=GuidedCaptureState.MULTIPLE_FACES), 3)
        self.collector.record(self.result(reason=GuidedCaptureState.NO_FACE), 0)
        self.collector.record(self.result(reason=GuidedCaptureState.MULTIPLE_FACES), 2)
        report = self.collector.report()
        self.assertEqual(dict(report.detected_face_count_histogram), {0: 1, 2: 1, 3: 1})
        self.assertEqual(report.rejection_controls[0].control, "multiple_faces")
        self.assertEqual(report.rejection_controls[0].occurrences, 2)

    def test_report_contains_no_images_embeddings_landmarks_or_identities(self):
        self.collector.record(self.result(accepted=True, visual=True), 1)
        keys = _all_keys(asdict(self.collector.report()))
        for forbidden in ("embedding", "image", "landmark", "temporary_identity"):
            self.assertFalse(any(forbidden in key for key in keys))


def _all_keys(value):
    if isinstance(value, dict):
        return [str(key).lower() for key in value] + [
            item for child in value.values() for item in _all_keys(child)
        ]
    if isinstance(value, (list, tuple)):
        return [item for child in value for item in _all_keys(child)]
    return []


if __name__ == "__main__": unittest.main()
