"""Best-effort administrative audit application service."""
from __future__ import annotations
import logging,uuid
from datetime import datetime,timezone
from .contracts import *
from .sanitizer import sanitize_message,sanitize_metadata

LOGGER=logging.getLogger(__name__)

class AuditService:
    def __init__(self,repository,*,enabled=True,metadata_max_items=20,metadata_value_max_length=256,message_max_length=500):
        self.repository=repository;self.enabled=enabled;self.metadata_max_items=metadata_max_items;self.metadata_value_max_length=metadata_value_max_length;self.message_max_length=message_max_length
    def record(self,action:AuditAction,entity_type:AuditEntityType,*,actor_user_id=None,actor_role=None,entity_id=None,success=True,message="",source="application",session_id=None,metadata=None)->AuditRecord:
        if not self.enabled:raise AuditError("audit is disabled")
        record=AuditRecord(str(uuid.uuid4()),datetime.now(timezone.utc),actor_user_id,actor_role,action,entity_type,entity_id,bool(success),sanitize_message(message,self.message_max_length),sanitize_message(source,120),session_id,sanitize_metadata(metadata,maximum_items=self.metadata_max_items,value_maximum_length=self.metadata_value_max_length))
        return self.repository.append(record)
    def safe_record(self,*args,**kwargs)->AuditOperationResult:
        if not self.enabled:return AuditOperationResult(False,"Auditoría deshabilitada")
        try:
            record=self.record(*args,**kwargs);return AuditOperationResult(True,"Evento administrativo auditado",record.audit_id)
        except Exception as exc:
            action=args[0].value if args and isinstance(args[0],AuditAction) else "UNKNOWN"
            LOGGER.warning("Administrative audit unavailable action=%s error_type=%s",action,type(exc).__name__)
            return AuditOperationResult(False,"No se pudo registrar la auditoría")

