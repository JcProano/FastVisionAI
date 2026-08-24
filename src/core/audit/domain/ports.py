"""Dependency-inversion ports for audit application workflows."""

from pathlib import Path
from typing import Protocol

from .models import AuditQuery, AuditRecord, AuditSummaryDTO


class AuditRepositoryPort(Protocol):
    def append(self, record: AuditRecord) -> AuditRecord: ...
    def query(
        self, query: AuditQuery, *, maximum_limit: int = 1000
    ) -> tuple[AuditRecord, ...]: ...
    def summary(self) -> AuditSummaryDTO: ...


class AuditExporterPort(Protocol):
    def export(
        self,
        records: tuple[AuditRecord, ...],
        destination: Path,
        *,
        overwrite: bool = False,
    ) -> int: ...
