from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from src.engine.alignment import AlignmentQuality
from src.engine.calibration.contracts import CalibrationSample, CalibrationSampleMetadata
from src.engine.calibration.dataset import (
    CalibrationDatasetError, CalibrationDatasetStore, ConsentRequiredError,
)


class CalibrationDatasetTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(); self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        vector = np.array([1, 0], dtype=np.float32); vector.setflags(write=False)
        metadata = CalibrationSampleMetadata(
            "session", "temporary-a", datetime.now(timezone.utc), "usb:0", (640, 480),
            AlignmentQuality.VALID, "arcface", "v1", "sha",
        )
        self.groups = {"temporary-a": (CalibrationSample(vector, metadata),)}

    def test_save_requires_consent_and_does_not_overwrite_by_default(self):
        store = CalibrationDatasetStore(enabled=True)
        manifest, archive = self.root / "manifest.json", self.root / "data.npz"
        with self.assertRaises(ConsentRequiredError):
            store.save(self.groups, manifest, archive, consent_confirmed=False)
        store.save(self.groups, manifest, archive, consent_confirmed=True)
        with self.assertRaises(CalibrationDatasetError):
            store.save(self.groups, manifest, archive, consent_confirmed=True)
        self.assertNotIn("embedding", manifest.read_text(encoding="utf-8").lower())

    def test_round_trip_and_corrupt_load_does_not_alter_existing_data(self):
        store = CalibrationDatasetStore(enabled=True)
        manifest, archive = self.root / "manifest.json", self.root / "data.npz"
        store.save(self.groups, manifest, archive, consent_confirmed=True)
        loaded = store.load(manifest, archive)
        self.assertEqual(tuple(loaded), ("temporary-a",))
        active = {"preserved": "unchanged"}
        archive.write_bytes(archive.read_bytes() + b"corrupt")
        with self.assertRaises(CalibrationDatasetError):
            store.load(manifest, archive)
        self.assertEqual(active, {"preserved": "unchanged"})

    def test_delete_session_reports_deleted_missing_and_no_secure_erasure(self):
        store = CalibrationDatasetStore(enabled=True)
        manifest, archive = self.root / "manifest.json", self.root / "data.npz"
        store.save(self.groups, manifest, archive, consent_confirmed=True)
        images = self.root / "images"; images.mkdir(); image = images / "face.jpg"
        image.write_bytes(b"image")
        result = store.delete_session(manifest, archive, images)
        self.assertEqual(set(result.deleted), {manifest, archive, image})
        self.assertFalse(result.secure_erasure_claimed)
        repeated = store.delete_session(manifest, archive, images)
        self.assertEqual(set(repeated.not_found), {manifest, archive})


if __name__ == "__main__": unittest.main()
