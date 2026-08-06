from __future__ import annotations

import unittest
from datetime import datetime, timezone

import numpy as np

from src.engine.alignment import AlignmentQuality
from src.engine.calibration.contracts import (
    CalibrationPolicy, CalibrationSample, CalibrationSampleMetadata, CalibrationWarning,
)
from src.engine.calibration.service import CalibrationError, CalibrationService


class CalibrationServiceTests(unittest.TestCase):
    def sample(self, identity, vector, *, session="session-a", quality=AlignmentQuality.VALID,
               source="usb:0", resolution=(640, 480)):
        value = np.asarray(vector, dtype=np.float32)
        value /= np.linalg.norm(value)
        return CalibrationSample(value, CalibrationSampleMetadata(
            session, identity, datetime.now(timezone.utc), source, resolution, quality,
            "arcface", "v1", "weights-sha",
        ))

    def controlled(self):
        return {
            "temporary-a": (
                self.sample("temporary-a", [1, 0]),
                self.sample("temporary-a", [.5, np.sqrt(.75)]),
            ),
            "temporary-b": (
                self.sample("temporary-b", [0, 1], session="session-b"),
                self.sample("temporary-b", [0, 1], session="session-b"),
            ),
        }

    def test_threshold_boundary_and_exact_far_frr(self):
        report = CalibrationService().calibrate(self.controlled(), [.5], "run")
        rates = report.threshold_rates[0]
        # similarity == threshold is accepted; only similarity < threshold is rejected.
        self.assertEqual(rates.genuine_rejected, 0)
        self.assertEqual(rates.total_genuine_pairs, 2)
        self.assertEqual(rates.frr, 0.0)
        # Two of four impostor pairs have score >= .5.
        self.assertEqual(rates.impostors_accepted, 2)
        self.assertEqual(rates.total_impostor_pairs, 4)
        self.assertEqual(rates.far, .5)

    def test_statistics_histograms_and_eer_are_analysis_only(self):
        report = CalibrationService(CalibrationPolicy(histogram_bins=4)).calibrate(
            self.controlled(), [0, .5, 1], "run"
        )
        self.assertEqual(report.genuine_distribution.pair_count, 2)
        self.assertEqual(sum(report.genuine_distribution.histogram_counts), 2)
        self.assertEqual(len(report.genuine_distribution.histogram_edges), 5)
        self.assertTrue(report.estimated_eer.estimated)
        self.assertIn("estimated", report.estimated_eer.__dataclass_fields__)
        self.assertNotIn("recommended_threshold", report.__dataclass_fields__)

    def test_single_session_low_quality_and_homogeneous_warnings(self):
        groups = {
            key: tuple(self.sample(key, [1, index + 1], quality=AlignmentQuality.LOW_QUALITY)
                       for index in range(2))
            for key in ("temporary-a", "temporary-b")
        }
        report = CalibrationService().calibrate(groups, [.5], "run")
        self.assertIn(CalibrationWarning.SINGLE_SESSION, report.warnings)
        self.assertIn(CalibrationWarning.LOW_QUALITY_PREDOMINATES, report.warnings)
        self.assertIn(CalibrationWarning.HOMOGENEOUS_CAPTURE_CONDITIONS, report.warnings)
        self.assertEqual(report.quality.valid_samples, 0)
        self.assertEqual(report.quality.low_quality_samples, 4)
        self.assertEqual(report.quality.genuine_pairs_with_low_quality, 2)
        self.assertEqual(report.quality.impostor_pairs_with_low_quality, 4)

    def test_impostor_sampling_is_deterministic_and_never_samples_genuine_pairs(self):
        groups = {
            key: tuple(self.sample(key, [1, identity_index + sample_index + .1])
                       for sample_index in range(4))
            for identity_index, key in enumerate(("temporary-a", "temporary-b", "temporary-c"))
        }
        policy = CalibrationPolicy(max_impostor_pairs=5, impostor_sampling_seed=17)
        first = CalibrationService(policy).calibrate(groups, [.5], "first")
        second = CalibrationService(policy).calibrate(groups, [.5], "second")
        self.assertEqual(first.total_possible_impostor_pairs, 48)
        self.assertEqual(first.used_impostor_pairs, 5)
        self.assertTrue(first.impostor_pairs_sampled)
        self.assertEqual(first.genuine_distribution.pair_count, 18)
        self.assertEqual(first.impostor_distribution, second.impostor_distribution)

    def test_metadata_and_model_provenance_validation(self):
        groups = self.controlled()
        bad = self.sample("temporary-b", [0, 1])
        from dataclasses import replace
        bad = replace(bad, metadata=replace(bad.metadata, model="other"))
        groups["temporary-b"] = (groups["temporary-b"][0], bad)
        with self.assertRaisesRegex(CalibrationError, "provenance") as caught:
            CalibrationService().calibrate(groups, [.5], "run")
        self.assertNotIn("[", str(caught.exception))

    def test_report_and_errors_never_contain_embedding_vectors(self):
        groups = self.controlled()
        report = CalibrationService().calibrate(groups, [.5], "run")
        rendered = repr(report).lower()
        self.assertNotIn("array(", rendered)
        self.assertNotIn("12345.125", rendered)
        invalid = np.array([12345.125, np.nan], dtype=np.float32)
        groups["temporary-a"] = (
            CalibrationSample(invalid, groups["temporary-a"][0].metadata),
            groups["temporary-a"][1],
        )
        with self.assertRaises(CalibrationError) as caught:
            CalibrationService().calibrate(groups, [.5], "run")
        self.assertNotIn("12345", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
