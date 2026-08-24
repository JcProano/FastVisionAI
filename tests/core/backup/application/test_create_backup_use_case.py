import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.core.backup.application import CreateBackupUseCase
from src.core.backup.domain import BackupRequest
from tests.core.backup.fakes import (
    FakeArchive,
    FakeCatalog,
    FakeContentValidator,
    FakeMaintenance,
    FakeSnapshots,
)


class CreateBackupUseCaseTests(unittest.TestCase):
    def test_empty_backup_has_explicit_manifest_and_maintenance_boundary(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            archive = FakeArchive()
            maintenance = FakeMaintenance()
            use_case = CreateBackupUseCase(
                FakeCatalog(root),
                archive,
                FakeSnapshots(),
                FakeContentValidator(),
                maintenance,
                application_version="test",
                new_id=lambda: "backup-1",
            )

            result = use_case.execute(BackupRequest(root / "backup.fvbackup"))

            self.assertTrue(result.success)
            self.assertEqual(result.backup_id, "backup-1")
            self.assertEqual(archive.created_manifest.files, ())
            self.assertEqual(
                maintenance.events, ["begin_backup", "end_backup"]
            )


if __name__ == "__main__":
    unittest.main()
