import unittest

from src.core.audit.application import RecordAuditUseCase, SafeRecordAuditUseCase
from src.core.audit.domain import AuditAction, AuditEntityType
from tests.core.audit.fakes import InMemoryAuditRepository


class SafeRecordAuditUseCaseTests(unittest.TestCase):
    def test_adapter_failure_is_best_effort(self) -> None:
        repository = InMemoryAuditRepository()
        repository.fail_append = True

        result = SafeRecordAuditUseCase(
            RecordAuditUseCase(repository)
        ).execute(AuditAction.LOGIN_FAILURE, AuditEntityType.SESSION)

        self.assertFalse(result.success)
        self.assertIsNone(result.audit_id)


if __name__ == "__main__":
    unittest.main()
