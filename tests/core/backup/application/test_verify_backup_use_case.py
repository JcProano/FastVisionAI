import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from src.core.backup.application import VerifyBackupUseCase
from src.core.backup.domain import BackupManifest
from tests.core.backup.fakes import FakeArchive


class VerifyBackupUseCaseTests(unittest.TestCase):
    def test_returns_safe_verification_projection(self) -> None:
        manifest = BackupManifest(
            1,
            datetime(2026, 1, 1, tzinfo=timezone.utc),
            "FastVisionAI",
            "test",
            "backup-1",
            "NONE",
            (),
            (),
        )
        with TemporaryDirectory() as directory:
            path = Path(directory) / "backup.fvbackup"
            path.write_bytes(b"backup")

            result = VerifyBackupUseCase(FakeArchive(manifest)).execute(path)

            self.assertTrue(result.valid)
            self.assertEqual(result.backup_id, "backup-1")


if __name__ == "__main__":
    unittest.main()
