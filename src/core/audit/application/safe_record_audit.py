"""Best-effort wrapper around the strict record-audit use case."""

from __future__ import annotations

import logging

from ..domain.models import (
    AuditAction,
    AuditEntityType,
    AuditOperationResult,
)
from .record_audit import RecordAuditUseCase

LOGGER = logging.getLogger(__name__)


class SafeRecordAuditUseCase:
    def __init__(self, recorder: RecordAuditUseCase) -> None:
        self._recorder = recorder

    def execute(
        self, action: AuditAction, entity_type: AuditEntityType, **arguments
    ) -> AuditOperationResult:
        if not self._recorder.enabled:
            return AuditOperationResult(False, "Auditoría deshabilitada")
        try:
            record = self._recorder.execute(action, entity_type, **arguments)
            return AuditOperationResult(
                True, "Evento administrativo auditado", record.audit_id
            )
        except Exception as exc:
            LOGGER.warning(
                "Administrative audit unavailable action=%s error_type=%s",
                action.value,
                type(exc).__name__,
            )
            return AuditOperationResult(
                False, "No se pudo registrar la auditoría"
            )
