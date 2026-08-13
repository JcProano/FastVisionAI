"""RBAC-enforced UI boundary for administrative audit."""
from __future__ import annotations
from pathlib import Path
from src.core.audit import AuditCSVExporter,AuditQuery,AuditRecordDTO
from src.core.security import AuthorizationPermission
from .contracts import AuditDashboardDTO,AuditListDTO,AuditUIResult

class AuditController:
 def __init__(self,repository,authorization,*,default_limit=200,maximum_limit=1000,exporter=None):self.repository=repository;self.authorization=authorization;self.default_limit=default_limit;self.maximum_limit=maximum_limit;self.exporter=exporter or AuditCSVExporter()
 def query(self,query:AuditQuery|None=None)->AuditListDTO:
  self._require(AuthorizationPermission.VIEW_AUDIT);query=query or AuditQuery(limit=self.default_limit)
  rows=self.repository.query(query,maximum_limit=self.maximum_limit)
  result=tuple(AuditRecordDTO(item.audit_id,item.timestamp_utc,item.actor_user_id,item.actor_role,item.action.value,item.entity_type.value,item.entity_id,item.success,item.message,item.source,item.session_id) for item in rows)
  return AuditListDTO(result,len(result),f"{len(result)} eventos administrativos")
 def summary(self)->AuditDashboardDTO:
  self._require(AuthorizationPermission.VIEW_AUDIT);item=self.repository.summary();return AuditDashboardDTO(item.total,item.successes,item.failures,item.latest_timestamp_utc)
 def export_csv(self,destination:Path,query:AuditQuery|None=None,*,overwrite=False)->AuditUIResult:
  self._require(AuthorizationPermission.EXPORT_AUDIT);rows=self.repository.query(query or AuditQuery(limit=self.maximum_limit),maximum_limit=self.maximum_limit);count=self.exporter.export(rows,destination,overwrite=overwrite);return AuditUIResult(True,f"{count} eventos exportados",count)
 def _require(self,permission):
  if not self.authorization.can(permission):raise PermissionError("operation is not authorized")

