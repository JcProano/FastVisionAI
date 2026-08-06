from __future__ import annotations

import unittest
from dataclasses import asdict
from datetime import datetime, timezone

import numpy as np

from src.engine.alignment import AlignmentQuality
from src.engine.calibration.contracts import CalibrationSample, CalibrationSampleMetadata
from src.engine.calibration.diagnostics import CalibrationDiagnosticService, DiagnosticPolicy


class CalibrationDiagnosticTests(unittest.TestCase):
    def sample(self, identity, session, vector, quality=AlignmentQuality.VALID):
        value = np.asarray(vector, dtype=np.float32)
        value = np.asarray(value / np.linalg.norm(value), dtype=np.float32)
        return CalibrationSample(value, CalibrationSampleMetadata(
            session, identity, datetime.now(timezone.utc), "usb:0", (640, 480), quality,
            "arcface", "v1", "sha",
        ))

    def groups(self):
        return {
            "temporary-a": (
                self.sample("temporary-a", "a-1", [1, 0]),
                self.sample("temporary-a", "a-1", [.99, .01], AlignmentQuality.LOW_QUALITY),
                self.sample("temporary-a", "a-2", [.8, .6]),
            ),
            "temporary-b": (
                self.sample("temporary-b", "b-1", [0, 1]),
                self.sample("temporary-b", "b-1", [.1, .99]),
            ),
        }

    def test_reports_identity_session_and_comparison_distributions(self):
        report = CalibrationDiagnosticService().analyze(self.groups())
        self.assertEqual([item.left for item in report.genuine_by_identity],
                         ["temporary-a", "temporary-b"])
        self.assertEqual(report.genuine_by_identity[0].similarity.count, 3)
        self.assertEqual(report.impostor_by_identity_pair[0].similarity.count, 6)
        self.assertEqual(report.within_session.count, 2)
        self.assertEqual(report.between_sessions_same_identity.count, 2)
        self.assertEqual(report.between_identities.count, 6)
        self.assertEqual(len(report.by_session), 3)
        self.assertEqual(len(report.similarity_matrix), 6)

    def test_samples_keep_quality_and_near_duplicate_references_without_vectors(self):
        report = CalibrationDiagnosticService(DiagnosticPolicy(
            near_duplicate_similarity=.99
        )).analyze(self.groups())
        first = report.samples[0]
        self.assertEqual(first.sample.alignment_quality, "valid")
        self.assertEqual(first.near_duplicate_with[0].alignment_quality, "low_quality")
        rendered = repr(asdict(report)).lower()
        self.assertNotIn("embedding", rendered)
        self.assertNotIn("array(", rendered)

    def test_flags_outlier_and_centroid_difference(self):
        groups = {"temporary-a": tuple(
            self.sample("temporary-a", "session", vector)
            for vector in ([1, .00], [1, .01], [1, -.01], [1, .02], [-1, 0])
        )}
        report = CalibrationDiagnosticService(DiagnosticPolicy(
            centroid_min_similarity=0.0, outlier_iqr_multiplier=1.5
        )).analyze(groups)
        last = report.samples[-1]
        self.assertTrue(last.outlier)
        self.assertTrue(last.excessively_different_from_identity_center)

    def test_warns_for_single_session_and_high_cross_identity_similarity_without_decision(self):
        groups = {
            "temporary-a": (self.sample("temporary-a", "a", [1, 0]),),
            "temporary-b": (self.sample("temporary-b", "b", [1, .01]),),
        }
        report = CalibrationDiagnosticService(DiagnosticPolicy(
            identity_pair_warning_similarity=.9
        )).analyze(groups)
        self.assertEqual(sum("only one session" in item for item in report.warnings), 2)
        warning = next(item for item in report.warnings if "unusually high" in item)
        self.assertIn("not an identity conclusion", warning)
        self.assertNotIn("same person", warning)

    def test_per_session_summary_handles_one_sample_without_fabricating_scores(self):
        groups = {"temporary-a": (self.sample("temporary-a", "single", [1, 0]),)}
        report = CalibrationDiagnosticService().analyze(groups)
        summary = report.by_session[0].similarity
        self.assertEqual(summary.count, 0)
        self.assertIsNone(summary.minimum)
        self.assertIsNone(summary.mean)


if __name__ == "__main__": unittest.main()
