"""RBAC-enforced, asynchronous-friendly backup application boundary."""
from __future__ import annotations
from collections import deque
from datetime import datetime,timezone
from pathlib import Path
from src.core.backup import BackupRequest
from src.core.security import AuthorizationPermission
from .contracts import BackupOperationDTO

class BackupController:
 def __init__(self,backup_service,restore_service,authorization,*,history_limit:int=50,prepare_for_restore=None):
  if history_limit<=0:raise ValueError("history_limit must be positive")
  self.backup_service=backup_service;self.restore_service=restore_service;self.authorization=authorization;self._history=deque(maxlen=history_limit);self.prepare_for_restore=prepare_for_restore
 def can_backup(self):return self.authorization.can(AuthorizationPermission.BACKUP)
 def can_restore(self):return self.authorization.can(AuthorizationPermission.RESTORE)
 def create(self,destination:Path,*,overwrite:bool=False):
  self._require(AuthorizationPermission.BACKUP)
  try:result=self.backup_service.create(BackupRequest(destination,overwrite));self._record("BACKUP",True,result.message);return result
  except Exception:self._record("BACKUP",False,"No se pudo crear el backup.");raise
 def verify(self,path:Path):
  self._require(AuthorizationPermission.BACKUP)
  try:result=self.backup_service.verify(path);self._record("VERIFY",True,result.message);return result
  except Exception:self._record("VERIFY",False,"El backup no superó la verificación.");raise
 def prepare_restore(self,path:Path):self._require(AuthorizationPermission.RESTORE);return self.restore_service.prepare(path)
 def restore(self,plan,*,confirmed:bool):
  self._require(AuthorizationPermission.RESTORE)
  try:
   if confirmed and self.prepare_for_restore:self.prepare_for_restore()
   result=self.restore_service.restore(plan,confirmed=confirmed);self._record("RESTORE",result.success,result.message);return result
  except Exception:self._record("RESTORE",False,"La restauración falló de forma segura.");raise
 def history(self):return tuple(self._history)
 def _require(self,permission):
  if not self.authorization.require(permission).allowed:raise PermissionError("operation is not authorized")
 def _record(self,operation,success,message):self._history.append(BackupOperationDTO(operation,success,datetime.now(timezone.utc),message))
