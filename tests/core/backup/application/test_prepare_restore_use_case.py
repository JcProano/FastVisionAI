import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from src.core.backup.application import PrepareRestoreUseCase
from src.core.backup.domain import BackupManifest
from tests.core.backup.fakes import (
    FakeArchive,
    FakeCatalog,
    FakeContentValidator,
    FakeSnapshots,
)


class PrepareRestoreUseCaseTests(unittest.TestCase):
    def test_stages_and_validates_without_mutating_destinations(self) -> None:
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
            root = Path(directory)
            archive_path = root / "backup.fvbackup"
            archive_path.write_bytes(b"backup")

            plan = PrepareRestoreUseCase(
                FakeCatalog(root),
                FakeArchive(manifest),
                FakeSnapshots(),
                FakeContentValidator(),
            ).execute(archive_path)

            self.assertEqual(plan.backup_id, "backup-1")
            self.assertEqual(plan.files, ())
            plan.staging_directory.rmdir()


if __name__ == "__main__":
    unittest.main()
