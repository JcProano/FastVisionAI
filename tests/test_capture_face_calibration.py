from __future__ import annotations

import unittest
import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone

import numpy as np

from src.camera.frame import Frame
from src.engine.alignment import AlignmentQuality
from src.engine.calibration.dataset import ConsentRequiredError, require_capture_consent
from src.engine.embedding.contracts import FaceEmbedding
from src.camera.camera_types import CameraType
from src.engine.calibration.contracts import CalibrationSampleType
from src.validation.capture_face_calibration import (
    CapturePolicy, CaptureSampleSelector, build_parser, capture_camera_config,
    parse_camera_source, run_capture, safe_source_reference,
)


class CaptureFaceCalibrationTests(unittest.TestCase):
    def embedding(self, vector, quality=AlignmentQuality.VALID):
        value = np.asarray(vector, dtype=np.float32); value /= np.linalg.norm(value)
        frame = Frame(np.zeros((2, 2, 3), dtype=np.uint8), 1, "mock", datetime.now(timezone.utc),
                      0, 2, 2, 1)
        return FaceEmbedding(frame, "run", 0, value, value.size, 1.0, quality, 1.0,
                             "mock", "arcface", "v1", "sha")

    def test_consent_required_only_when_artifacts_are_requested(self):
        require_capture_consent(save_data=False, save_images=False, consent_confirmed=False)
        for save_data, save_images in ((True, False), (False, True)):
            with self.assertRaises(ConsentRequiredError):
                require_capture_consent(save_data=save_data, save_images=save_images,
                                        consent_confirmed=False)

    def test_selector_enforces_time_quality_and_near_duplicate_filters(self):
        selector = CaptureSampleSelector(CapturePolicy(2, 4, 1.0, .999))
        self.assertTrue(selector.consider(self.embedding([1, 0]), 1.0))
        self.assertFalse(selector.consider(self.embedding([0, 1]), 1.5))
        self.assertFalse(selector.consider(self.embedding([1, 0]), 2.0))
        self.assertFalse(selector.consider(
            self.embedding([0, 1], AlignmentQuality.LOW_QUALITY), 2.0
        ))
        self.assertTrue(selector.consider(self.embedding([0, 1]), 2.0))

    def test_source_parser_accepts_usb_and_supported_network_urls(self):
        self.assertEqual(parse_camera_source("0"), 0)
        self.assertEqual(parse_camera_source("1"), 1)
        for url in (
            "http://192.168.1.3:4747/video", "https://camera.example/video",
            "rtsp://camera.example/live", "rtsps://camera.example/live",
        ):
            self.assertEqual(parse_camera_source(url), url)

    def test_source_parser_rejects_ambiguous_or_invalid_values(self):
        for value in ("-1", "camera.mp4", "ftp://camera/live", "rtsp:///missing-host"):
            with self.subTest(value=value), self.assertRaises(Exception):
                parse_camera_source(value)

    def test_camera_type_is_derived_from_normalized_source(self):
        self.assertIs(capture_camera_config(0).camera_type, CameraType.USB)
        self.assertIs(capture_camera_config("http://camera/video").camera_type,
                      CameraType.NETWORK_HTTP)
        self.assertIs(capture_camera_config("https://camera/video").camera_type,
                      CameraType.NETWORK_HTTP)
        self.assertIs(capture_camera_config("rtsp://camera/live").camera_type,
                      CameraType.RTSP)
        self.assertIs(capture_camera_config("rtsps://camera/live").camera_type,
                      CameraType.RTSP)

    def test_source_reference_redacts_credentials_and_preserves_overlap(self):
        raw = "rtsp://admin:password@192.168.1.50:554/stream1?token=secret"
        reference = safe_source_reference(raw)
        self.assertEqual(reference, "rtsp://***:***@192.168.1.50:554/stream1")
        self.assertEqual(safe_source_reference(reference), reference)
        self.assertNotIn("password", reference)
        self.assertNotIn("secret", reference)

    def test_redacted_network_source_keeps_enrollment_overlap_protection(self):
        raw = "rtsp://admin:password@camera.example/live?token=secret"
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "gallery.json"
            manifest.write_text(json.dumps({
                "identities": [{"person_id": "registered"}],
                "templates": [{"source_reference": raw}],
            }), encoding="utf-8")
            args = build_parser(CalibrationSampleType.GENUINE).parse_args([
                "--temporary-id", "evaluation", "--gallery-manifest", str(manifest),
                "--expected-identity", "registered", "--confirm-sample-type",
                "CONFIRM GENUINE", "--illumination", "NORMAL", "--distance",
                "OPERATIONAL", "--pose", "FRONTAL",
                "--max-near-duplicate-similarity", "0.98", "--source", raw,
            ])
            with self.assertRaisesRegex(ValueError, "overlaps enrollment"):
                run_capture(args)

    def test_genuine_and_impostor_parsers_accept_network_source(self):
        required = ["--temporary-id", "subject", "--gallery-manifest", "gallery.json",
                    "--confirm-sample-type", "CONFIRM GENUINE", "--illumination", "NORMAL",
                    "--distance", "OPERATIONAL", "--pose", "FRONTAL",
                    "--max-near-duplicate-similarity", "0.98", "--source"]
        genuine = build_parser(CalibrationSampleType.GENUINE).parse_args(
            required + ["http://camera/video"])
        self.assertEqual(genuine.source, "http://camera/video")
        impostor_args = list(required)
        impostor_args[impostor_args.index("CONFIRM GENUINE")] = "CONFIRM IMPOSTOR"
        impostor = build_parser(CalibrationSampleType.IMPOSTOR).parse_args(
            impostor_args + ["rtsp://camera/live"])
        self.assertEqual(impostor.source, "rtsp://camera/live")


if __name__ == "__main__": unittest.main()
