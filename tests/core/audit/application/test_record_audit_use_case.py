import unittest
from datetime import datetime, timezone

from src.core.audit.application import RecordAuditUseCase
from src.core.audit.domain import AuditAction, AuditEntityType
from tests.core.audit.fakes import InMemoryAuditRepository


class RecordAuditUseCaseTests(unittest.TestCase):
    def test_sanitizes_and_appends_a_record(self) -> None:
        repository = InMemoryAuditRepository()
        moment = datetime(2026, 1, 1, tzinfo=timezone.utc)
        use_case = RecordAuditUseCase(
            repository,
            now=lambda: moment,
            new_id=lambda: "audit-1",
            message_max_length=5,
        )

        record = use_case.execute(
            AuditAction.CONFIG_SAVED,
            AuditEntityType.CONFIGURATION,
            message="abcdefgh",
            metadata={"password": "secret"},
        )

        self.assertEqual(record.message, "abcde")
        self.assertEqual(record.metadata["password"], "[REDACTED]")
        self.assertIs(repository.records[0], record)


if __name__ == "__main__":
    unittest.main()
