"""In-memory ports for audit application tests."""

from pathlib import Path

from src.core.audit.domain import (
    AuditQuery,
    AuditRecord,
    AuditSummaryDTO,
)


class InMemoryAuditRepository:
    def __init__(self) -> None:
        self.records: list[AuditRecord] = []
        self.fail_append = False
        self.query_limits: list[int] = []

    def append(self, record: AuditRecord) -> AuditRecord:
        if self.fail_append:
            raise OSError("simulated unavailable audit store")
        self.records.append(record)
        return record

    def query(
        self, query: AuditQuery, *, maximum_limit: int = 1000
    ) -> tuple[AuditRecord, ...]:
        del query
        self.query_limits.append(maximum_limit)
        return tuple(self.records[:maximum_limit])

    def summary(self) -> AuditSummaryDTO:
        successes = sum(record.success for record in self.records)
        latest = self.records[-1].timestamp_utc if self.records else None
        return AuditSummaryDTO(
            len(self.records), successes, len(self.records) - successes, latest
        )


class FakeAuditExporter:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[AuditRecord, ...], Path, bool]] = []

    def export(
        self,
        records: tuple[AuditRecord, ...],
        destination: Path,
        *,
        overwrite: bool = False,
    ) -> int:
        self.calls.append((records, destination, overwrite))
        return len(records)
