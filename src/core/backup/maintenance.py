"""Application-level quiescence coordination without domain coupling."""
from __future__ import annotations
import threading
from collections.abc import Callable
from .contracts import MaintenanceState,RestoreError

class ApplicationMaintenanceCoordinator:
 def __init__(self):self._state=MaintenanceState.RUNNING;self._lock=threading.RLock();self._active=0
 @property
 def state(self):
  with self._lock:return self._state
 def begin_operation(self):
  with self._lock:
   if self._state not in {MaintenanceState.RUNNING,MaintenanceState.BACKUP_IN_PROGRESS}:raise RestoreError("administrative operations are suspended")
   self._active+=1
 def end_operation(self):
  with self._lock:self._active=max(0,self._active-1)
 def begin_backup(self):
  with self._lock:
   if self._state is not MaintenanceState.RUNNING:raise RestoreError("maintenance operation already active")
   self._state=MaintenanceState.BACKUP_IN_PROGRESS
 def end_backup(self):
  with self._lock:
   if self._state is MaintenanceState.BACKUP_IN_PROGRESS:self._state=MaintenanceState.RUNNING
 def quiesce(self,*,cancel_enrollment:Callable[[],object],close_session:Callable[[],bool],close_windows:Callable[[],None],cancel_callbacks:Callable[[],None],timeout_seconds:float):
  with self._lock:
   if self._state not in {MaintenanceState.RUNNING,MaintenanceState.BACKUP_IN_PROGRESS}:raise RestoreError("cannot enter quiescence")
   self._state=MaintenanceState.QUIESCING
  try:
   cancel_enrollment();cancel_callbacks();close_windows()
   if not close_session():raise RestoreError("live worker did not stop before timeout")
   with self._lock:
    if self._active:raise RestoreError("administrative operations remain active")
    self._state=MaintenanceState.QUIESCENT
  except Exception:
   with self._lock:self._state=MaintenanceState.FAILED
   raise
 def begin_restore(self):
  with self._lock:
   if self._state is not MaintenanceState.QUIESCENT:raise RestoreError("restore requires QUIESCENT state")
   self._state=MaintenanceState.RESTORING
 def complete_restore(self):
  with self._lock:
   if self._state is MaintenanceState.RESTORING:self._state=MaintenanceState.QUIESCENT
 def fail(self):
  with self._lock:self._state=MaintenanceState.FAILED
