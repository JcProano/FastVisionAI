"""Compatibility facade for explicit administrative-audit use cases."""

from __future__ import annotations

from .application import RecordAuditUseCase, SafeRecordAuditUseCase


class AuditService:
    def __init__(
        self,
        repository,
        *,
        enabled=True,
        metadata_max_items=20,
        metadata_value_max_length=256,
        message_max_length=500,
    ) -> None:
        self.repository = repository
        self.metadata_max_items = metadata_max_items
        self.metadata_value_max_length = metadata_value_max_length
        self.message_max_length = message_max_length
        self._record = RecordAuditUseCase(
            repository,
            enabled=enabled,
            metadata_max_items=metadata_max_items,
            metadata_value_max_length=metadata_value_max_length,
            message_max_length=message_max_length,
        )
        self._safe_record = SafeRecordAuditUseCase(self._record)
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = bool(value)
        if hasattr(self, "_record"):
            self._record.enabled = self._enabled

    def record(self, action, entity_type, **arguments):
        return self._record.execute(action, entity_type, **arguments)

    def safe_record(self, action, entity_type, **arguments):
        return self._safe_record.execute(action, entity_type, **arguments)
