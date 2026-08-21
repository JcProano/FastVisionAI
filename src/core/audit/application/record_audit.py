"""Create and append one sanitized administrative audit record."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping
from datetime import datetime, timezone

from ..domain.models import AuditAction, AuditEntityType, AuditError, AuditRecord
from ..domain.ports import AuditRepositoryPort
from ..domain.sanitization import sanitize_message, sanitize_metadata


class RecordAuditUseCase:
    def __init__(
        self,
        repository: AuditRepositoryPort,
        *,
        enabled: bool = True,
        metadata_max_items: int = 20,
        metadata_value_max_length: int = 256,
        message_max_length: int = 500,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        new_id: Callable[[], str] = lambda: str(uuid.uuid4()),
    ) -> None:
        self.repository = repository
        self.enabled = enabled
        self.metadata_max_items = metadata_max_items
        self.metadata_value_max_length = metadata_value_max_length
        self.message_max_length = message_max_length
        self._now = now
        self._new_id = new_id

    def execute(
        self,
        action: AuditAction,
        entity_type: AuditEntityType,
        *,
        actor_user_id: str | None = None,
        actor_role: str | None = None,
        entity_id: str | None = None,
        success: bool = True,
        message: str = "",
        source: str = "application",
        session_id: str | None = None,
        metadata: Mapping[str, object] | None = None,
    ) -> AuditRecord:
        if not self.enabled:
            raise AuditError("audit is disabled")
        record = AuditRecord(
            self._new_id(),
            self._now(),
            actor_user_id,
            actor_role,
            action,
            entity_type,
            entity_id,
            bool(success),
            sanitize_message(message, self.message_max_length),
            sanitize_message(source, 120),
            session_id,
            sanitize_metadata(
                metadata,
                maximum_items=self.metadata_max_items,
                value_maximum_length=self.metadata_value_max_length,
            ),
        )
        return self.repository.append(record)
