import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from src.core.backup.application import RestoreBackupUseCase
from src.core.backup.domain import RestorePlan
from tests.core.backup.fakes import FakeCatalog, FakeMaintenance


class RestoreBackupUseCaseTests(unittest.TestCase):
    def test_commits_an_empty_staged_plan_through_maintenance(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            staging = root / "staging"
            staging.mkdir()
            maintenance = FakeMaintenance()
            plan = RestorePlan(
                "backup-1", root / "backup.fvbackup", staging, (), 0
            )

            result = RestoreBackupUseCase(
                FakeCatalog(root), maintenance, replace=os.replace
            ).execute(plan, confirmed=True)

            self.assertTrue(result.success)
            self.assertEqual(
                maintenance.events, ["begin_restore", "complete_restore"]
            )


if __name__ == "__main__":
    unittest.main()
