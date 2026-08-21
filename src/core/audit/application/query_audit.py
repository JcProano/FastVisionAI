"""Query administrative audit records with an enforced adapter-side limit."""

from ..domain.models import AuditQuery, AuditRecord
from ..domain.ports import AuditRepositoryPort


class QueryAuditUseCase:
    def __init__(
        self, repository: AuditRepositoryPort, *, maximum_limit: int = 1000
    ) -> None:
        self._repository = repository
        self.maximum_limit = maximum_limit

    def execute(self, query: AuditQuery) -> tuple[AuditRecord, ...]:
        return self._repository.query(query, maximum_limit=self.maximum_limit)
