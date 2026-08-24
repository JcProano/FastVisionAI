"""Query and export administrative audit records through explicit ports."""

from pathlib import Path

from ..domain.models import AuditQuery
from ..domain.ports import AuditExporterPort, AuditRepositoryPort


class ExportAuditUseCase:
    def __init__(
        self,
        repository: AuditRepositoryPort,
        exporter: AuditExporterPort,
        *,
        maximum_limit: int = 1000,
    ) -> None:
        self._repository = repository
        self._exporter = exporter
        self.maximum_limit = maximum_limit

    def execute(
        self,
        destination: Path,
        query: AuditQuery,
        *,
        overwrite: bool = False,
    ) -> int:
        records = self._repository.query(
            query, maximum_limit=self.maximum_limit
        )
        return self._exporter.export(
            records, destination, overwrite=overwrite
        )
