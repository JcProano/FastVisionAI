from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from src.engine.alignment import AlignmentQuality
from src.engine.calibration.contracts import (
    CalibrationDistance, CalibrationIllumination, CalibrationPose, CalibrationSample,
    CalibrationSampleMetadata, CalibrationSampleType,
)
from src.engine.calibration.recognition import (
    RecognitionCalibrationError, RecognitionCalibrationPolicy,
    analyze_recognition_calibration, validate_approved_calibration,
)
from src.engine.embedding.contracts import FaceEmbedding
from src.engine.gallery import FaceGallery, FaceIdentity, FaceMatcher, MatchPolicy
from src.engine.gallery.persistence import GalleryPersistence
from src.engine.recognition import RecognitionPolicy, RecognitionService, RecognitionState
from src.ui.identification import IdentificationPopupPolicy, IdentificationPresentationController
from src.ui.recognition_session import ExperimentalRecognitionSession
from src.validation.approve_recognition_calibration import approve


class RC17RecognitionCalibrationTests(unittest.TestCase):
    def vector(self, values):
        value = np.asarray(values, dtype=np.float32); value /= np.linalg.norm(value)
        return value

    def gallery(self):
        gallery = FaceGallery(); gallery.register_identity(FaceIdentity("registered", "Jean"))
        embedding = self.embedding([1, 0], run="enrollment")
        gallery.add_template("registered", embedding, source_reference="enrollment-source")
        return gallery

    def embedding(self, values, *, run="evaluation", sha="sha"):
        from src.camera.frame import Frame
        frame = Frame(np.zeros((2, 2, 3), dtype=np.uint8), 1, "camera",
                      datetime.now(timezone.utc), 0, 2, 2, 1)
        vector = self.vector(values)
        return FaceEmbedding(frame, run, 0, vector, 2, 1, AlignmentQuality.VALID,
                             1, "cpu", "w600k_mbf", "buffalo_sc-v0.7", sha)

    def sample(self, subject, values, kind, index, *, session="session-1", sha="sha"):
        return CalibrationSample(self.vector(values), CalibrationSampleMetadata(
            session, subject, datetime.now(timezone.utc), "camera-evaluation", (640, 480),
            AlignmentQuality.VALID, "w600k_mbf", "buffalo_sc-v0.7", sha,
            sample_type=kind,
            expected_identity="registered" if kind is CalibrationSampleType.GENUINE else None,
            calibration_session_id=session, evaluation_sample_id=f"sample-{index}",
            condition_id="normal-operational-frontal",
            illumination=CalibrationIllumination.NORMAL,
            distance=CalibrationDistance.OPERATIONAL, pose=CalibrationPose.FRONTAL,
        ))

    def groups(self):
        return {
            "registered-evaluation": (
                self.sample("registered-evaluation", [0.99, .1],
                            CalibrationSampleType.GENUINE, 1, session="session-1"),
                self.sample("registered-evaluation", [.98, .2],
                            CalibrationSampleType.GENUINE, 2, session="session-2"),
            ),
            "external-1": (
                self.sample("external-1", [.1, .99], CalibrationSampleType.IMPOSTOR, 3),
            ),
        }

    def test_reference_evaluation_metrics_and_single_identity_ambiguity(self):
        policy = RecognitionCalibrationPolicy(2, 2, 1, 1, 0, 0, .1)
        report = analyze_recognition_calibration(self.gallery(), self.groups(), policy)
        self.assertTrue(report["candidate_supported"])
        self.assertEqual(report["genuine_samples"], 2)
        self.assertEqual(report["impostor_samples"], 1)
        self.assertIsNone(report["ambiguity_analysis"])
        self.assertEqual(report["distribution_margin"],
                         report["minimum_genuine_similarity"] -
                         report["maximum_impostor_similarity"])
        self.assertEqual(list(report["threshold_matrix"][0]),
                         ["threshold", "tp", "fn", "fp", "tn", "tar", "frr", "far"])

    def test_gallery_template_and_changed_weights_are_rejected(self):
        groups = self.groups()
        exact = self.sample("registered-evaluation", [1, 0],
                            CalibrationSampleType.GENUINE, 8)
        groups["registered-evaluation"] = (exact, groups["registered-evaluation"][1])
        with self.assertRaisesRegex(RecognitionCalibrationError, "gallery template"):
            analyze_recognition_calibration(self.gallery(), groups,
                RecognitionCalibrationPolicy(2, 1, 1, 1, 1, 1, 0))
        bad = replace(self.groups()["external-1"][0], metadata=replace(
            self.groups()["external-1"][0].metadata, weights_sha256="other"))
        with self.assertRaisesRegex(RecognitionCalibrationError, "provenance"):
            analyze_recognition_calibration(self.gallery(), {
                **self.groups(), "external-1": (bad,)})

    def test_not_evaluated_unknown_match_ambiguous_and_non_deciding_matcher(self):
        gallery = self.gallery(); matcher = FaceMatcher(2, MatchPolicy(False, None))
        disabled = RecognitionService(gallery, matcher, RecognitionPolicy(top_k=2))
        dto, _ = ExperimentalRecognitionSession(disabled).query(self.embedding([1, .01]))
        self.assertIn("AÚN NO CALIBRADO", dto.message)
        self.assertFalse(dto.evaluated)
        popup = IdentificationPresentationController(IdentificationPopupPolicy(), object())
        self.assertEqual(popup.observe(dto).popup_type.value, "SUPPRESSED")
        active = RecognitionService(gallery, matcher, RecognitionPolicy(
            True, .8, None, top_k=2, allow_low_quality=False))
        match = active.recognize(self.embedding([1, .01]))
        unknown = active.recognize(self.embedding([.1, 1]))
        self.assertEqual((match.state, match.evaluated), (RecognitionState.MATCH, True))
        self.assertEqual((unknown.state, unknown.evaluated), (RecognitionState.UNKNOWN, True))
        self.assertFalse(matcher.policy.automatic_decision_enabled)
        self.assertIsNone(matcher.policy.threshold)

    def test_invalid_artifact_weights_and_quality_similarity_independence(self):
        gallery = self.gallery()
        artifact = {
            "model_name": "w600k_mbf", "model_version": "buffalo_sc-v0.7",
            "weights_sha256": "other", "selected_threshold": .8,
            "selected_ambiguity_margin": None, "source_report_sha256": "hash",
            "approved_at": "now",
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "artifact.json"; path.write_text(json.dumps(artifact))
            with self.assertRaisesRegex(RecognitionCalibrationError, "provenance"):
                validate_approved_calibration(path, gallery,
                    {"match_threshold": .8, "ambiguity_margin": None})
        policy = RecognitionPolicy(True, .8, None, top_k=2, minimum_quality_score=75)
        service = RecognitionService(gallery, FaceMatcher(2), policy)
        result = service.recognize(self.embedding([1, .01]), None)
        self.assertAlmostEqual(result.similarity, 0.99995005, places=5)
        self.assertEqual(result.state, RecognitionState.NOT_EVALUATED)
        self.assertFalse(result.evaluated)

    def test_explicit_approval_writes_separate_profile_and_preserves_matcher(self):
        report = analyze_recognition_calibration(
            self.gallery(), self.groups(), RecognitionCalibrationPolicy(2, 2, 1, 1, 0, 0, .1))
        threshold = report["supported_thresholds"][0]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); manifest = root / "gallery.json"; archive = root / "gallery.npz"
            GalleryPersistence(enabled=True).export(self.gallery(), manifest, archive)
            report_path = root / "report.json"
            report_path.write_text(json.dumps(report, sort_keys=True), encoding="utf-8")
            safe = root / "safe.json"
            safe.write_text(json.dumps({
                "profile_name": "safe", "matcher": {
                    "automatic_decision_enabled": False, "threshold": None, "top_k": 2},
                "recognition": {"automatic_decision_enabled": False,
                    "match_threshold": None, "ambiguity_margin": None},
            }), encoding="utf-8")
            artifact_path = root / "calibration.json"; active = root / "active.json"
            artifact, profile = approve(report_path, threshold, None, manifest, archive,
                                        safe, artifact_path, active)
            self.assertEqual(artifact["source_report_sha256"],
                             __import__("hashlib").sha256(report_path.read_bytes()).hexdigest())
            self.assertFalse(profile["matcher"]["automatic_decision_enabled"])
            self.assertIsNone(profile["matcher"]["threshold"])
            self.assertTrue(profile["recognition"]["automatic_decision_enabled"])
            self.assertFalse(safe.read_text().find('"automatic_decision_enabled": true') >= 0)

    def test_ambiguous_requires_second_identity_and_approved_margin(self):
        gallery = self.gallery(); gallery.register_identity(FaceIdentity("other", "Other"))
        gallery.add_template("other", self.embedding([.99, .1]))
        service = RecognitionService(gallery, FaceMatcher(3), RecognitionPolicy(
            True, .8, .02, top_k=3))
        result = service.recognize(self.embedding([1, .05]))
        self.assertEqual(result.state, RecognitionState.AMBIGUOUS)
        self.assertTrue(result.evaluated)


if __name__ == "__main__":
    unittest.main()
