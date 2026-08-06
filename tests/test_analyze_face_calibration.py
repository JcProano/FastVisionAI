from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from src.engine.alignment import AlignmentQuality
from src.engine.calibration.contracts import CalibrationSample, CalibrationSampleMetadata
from src.engine.calibration.dataset import CalibrationDatasetError, CalibrationDatasetStore
from src.validation.analyze_face_calibration import load_calibration_input


class AnalyzeFaceCalibrationTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory(); self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.store = CalibrationDatasetStore(enabled=True)

    def sample(self, identity: str, session: str, vector=(1.0, 0.0), *, sha="sha", model="arc"):
        value = np.asarray(vector, dtype=np.float32)
        value /= np.linalg.norm(value)
        return CalibrationSample(value, CalibrationSampleMetadata(
            session, identity, datetime.now(timezone.utc), "usb:0", (640, 480),
            AlignmentQuality.VALID, model, "v1", sha,
        ))

    def save(self, directory: Path, groups):
        directory.mkdir(parents=True)
        self.store.save(groups, directory / "manifest.json", directory / "embeddings.npz",
                        consent_confirmed=True)

    def test_loads_a_single_session_directory(self):
        session = self.root / "session-a"
        self.save(session, {"temporary-a": (self.sample("temporary-a", "session-a"),)})
        loaded = load_calibration_input(session)
        self.assertEqual(tuple(loaded), ("temporary-a",))

    def test_root_discovers_multiple_sessions_and_distinct_identities(self):
        self.save(self.root / "b", {"temporary-b": (self.sample("temporary-b", "b", (0, 1)),)})
        self.save(self.root / "a", {"temporary-a": (self.sample("temporary-a", "a"),)})
        loaded = load_calibration_input(self.root)
        self.assertEqual(tuple(loaded), ("temporary-a", "temporary-b"))

    def test_same_identity_across_sessions_is_combined_with_session_metadata(self):
        self.save(self.root / "a", {"temporary-a": (self.sample("temporary-a", "a"),)})
        self.save(self.root / "b", {"temporary-a": (self.sample("temporary-a", "b", (.9, .1)),)})
        loaded = load_calibration_input(self.root)
        self.assertEqual(len(loaded["temporary-a"]), 2)
        self.assertEqual([item.metadata.session_id for item in loaded["temporary-a"]], ["a", "b"])

    def test_corrupt_or_incomplete_session_is_not_hidden(self):
        session = self.root / "broken"; session.mkdir()
        (session / "manifest.json").write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(CalibrationDatasetError, "incomplete.*broken"):
            load_calibration_input(self.root)

        session.joinpath("embeddings.npz").write_bytes(b"not-an-npz")
        with self.assertRaisesRegex(CalibrationDatasetError, "corrupt.*broken"):
            load_calibration_input(self.root)

    def test_irrelevant_directory_is_ignored_with_warning(self):
        (self.root / "notes").mkdir()
        self.save(self.root / "session", {"temporary-a": (self.sample("temporary-a", "s"),)})
        with self.assertLogs("src.validation.analyze_face_calibration", level="WARNING") as logs:
            loaded = load_calibration_input(self.root)
        self.assertIn("notes", " ".join(logs.output))
        self.assertEqual(tuple(loaded), ("temporary-a",))

    def test_incompatible_model_or_sha_is_rejected_across_sessions(self):
        for field, value in (("model", "other"), ("sha", "other-sha")):
            with self.subTest(field=field):
                root = self.root / field; root.mkdir()
                self.save(root / "a", {"temporary-a": (self.sample("temporary-a", "a"),)})
                kwargs = {field: value}
                self.save(root / "b", {"temporary-b": (
                    self.sample("temporary-b", "b", (0, 1), **kwargs),
                )})
                with self.assertRaisesRegex(CalibrationDatasetError, "incompatible"):
                    load_calibration_input(root)


if __name__ == "__main__": unittest.main()
