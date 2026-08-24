import unittest

from src.core.audit.application import SummarizeAuditUseCase
from tests.core.audit.fakes import InMemoryAuditRepository


class SummarizeAuditUseCaseTests(unittest.TestCase):
    def test_reads_the_summary_projection(self) -> None:
        summary = SummarizeAuditUseCase(InMemoryAuditRepository()).execute()

        self.assertEqual((summary.total, summary.successes, summary.failures), (0, 0, 0))


if __name__ == "__main__":
    unittest.main()
