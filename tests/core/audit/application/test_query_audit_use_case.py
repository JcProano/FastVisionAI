import unittest

from src.core.audit.application import QueryAuditUseCase
from src.core.audit.domain import AuditQuery
from tests.core.audit.fakes import InMemoryAuditRepository


class QueryAuditUseCaseTests(unittest.TestCase):
    def test_enforces_the_configured_repository_limit(self) -> None:
        repository = InMemoryAuditRepository()

        self.assertEqual(
            QueryAuditUseCase(repository, maximum_limit=25).execute(AuditQuery()),
            (),
        )
        self.assertEqual(repository.query_limits, [25])


if __name__ == "__main__":
    unittest.main()
