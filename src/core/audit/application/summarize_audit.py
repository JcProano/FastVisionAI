"""Read the administrative audit summary projection."""

from ..domain.models import AuditSummaryDTO
from ..domain.ports import AuditRepositoryPort


class SummarizeAuditUseCase:
    def __init__(self, repository: AuditRepositoryPort) -> None:
        self._repository = repository

    def execute(self) -> AuditSummaryDTO:
        return self._repository.summary()
