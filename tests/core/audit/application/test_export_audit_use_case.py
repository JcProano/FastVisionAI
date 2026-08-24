import unittest
from pathlib import Path

from src.core.audit.application import ExportAuditUseCase
from src.core.audit.domain import AuditQuery
from tests.core.audit.fakes import FakeAuditExporter, InMemoryAuditRepository


class ExportAuditUseCaseTests(unittest.TestCase):
    def test_queries_then_delegates_to_the_export_port(self) -> None:
        repository = InMemoryAuditRepository()
        exporter = FakeAuditExporter()
        destination = Path("audit.csv")

        count = ExportAuditUseCase(
            repository, exporter, maximum_limit=20
        ).execute(destination, AuditQuery(), overwrite=True)

        self.assertEqual(count, 0)
        self.assertEqual(repository.query_limits, [20])
        self.assertEqual(exporter.calls, [((), destination, True)])


if __name__ == "__main__":
    unittest.main()
