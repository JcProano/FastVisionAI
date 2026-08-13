"""Injectable read-only health providers."""
from __future__ import annotations
import sqlite3,time
from datetime import datetime,timezone
from pathlib import Path
from typing import Protocol
from .contracts import ComponentHealthDTO,HealthLevel

def _now():return datetime.now(timezone.utc)
class HealthProvider(Protocol):
 @property
 def component(self)->str:...
 def check(self)->ComponentHealthDTO:...

class CameraHealthProvider:
 component="camera"
 def __init__(self,*,enabled,worker_alive,camera_state,last_frame_monotonic,stale_frame_seconds=3.0,monotonic=time.monotonic):self.enabled=enabled;self.worker_alive=worker_alive;self.camera_state=camera_state;self.last_frame=last_frame_monotonic;self.stale=stale_frame_seconds;self.monotonic=monotonic
 def check(self):
  if not self.enabled():return ComponentHealthDTO(self.component,HealthLevel.DISABLED,"Cámara deshabilitada",_now())
  state=self.camera_state();last=self.last_frame()
  if state is None:return ComponentHealthDTO(self.component,HealthLevel.UNKNOWN,"Estado de cámara no disponible",_now())
  if str(state).casefold() not in {"connected","active","ok"} or not self.worker_alive():return ComponentHealthDTO(self.component,HealthLevel.ERROR,"Cámara o worker no operativo",_now())
  if last is None:return ComponentHealthDTO(self.component,HealthLevel.UNKNOWN,"Aún no se observan frames",_now())
  if self.monotonic()-last>self.stale:return ComponentHealthDTO(self.component,HealthLevel.WARNING,"Último frame desactualizado",_now())
  return ComponentHealthDTO(self.component,HealthLevel.OK,"Cámara operativa",_now())

class WorkerHealthProvider:
 component="worker"
 def __init__(self,alive,session_state=lambda:"running",enrollment_active=lambda:False,queue_depth=lambda:None):self.alive=alive;self.session_state=session_state;self.enrollment_active=enrollment_active;self.queue_depth=queue_depth
 def check(self):
  if not self.alive():return ComponentHealthDTO(self.component,HealthLevel.ERROR,"Worker detenido",_now())
  try:depth=self.queue_depth()
  except Exception:return ComponentHealthDTO(self.component,HealthLevel.ERROR,"Estado de colas no disponible",_now())
  suffix="; enrollment activo" if self.enrollment_active() else ""
  return ComponentHealthDTO(self.component,HealthLevel.OK,f"Worker activo; cola {depth if depth is not None else 'N/D'}{suffix}",_now())

class RuntimeHealthProvider:
 component="runtime"
 def __init__(self,state):self.state=state
 def check(self):
  state=self.state()
  if state is None or str(state).casefold() in {"n/d","unknown"}:return ComponentHealthDTO(self.component,HealthLevel.UNKNOWN,"Runtime sin información",_now())
  if str(state).casefold() in {"initialized","loaded","active","running"}:return ComponentHealthDTO(self.component,HealthLevel.OK,"Runtime operativo",_now())
  if str(state).casefold() in {"released","failed","error"}:return ComponentHealthDTO(self.component,HealthLevel.ERROR,"Runtime no operativo",_now())
  return ComponentHealthDTO(self.component,HealthLevel.WARNING,"Estado de Runtime no habitual",_now())

class SQLiteDatabaseHealthProvider:
 def __init__(self,component:str,path:Path,*,enabled=True,timeout=1.0):self.component=component;self.path=path;self.enabled=enabled;self.timeout=timeout
 def check(self):
  if not self.enabled:return ComponentHealthDTO(self.component,HealthLevel.DISABLED,"Módulo deshabilitado",_now())
  if not self.path.is_file():return ComponentHealthDTO(self.component,HealthLevel.UNKNOWN,"Base no disponible",_now())
  connection=None
  try:
   connection=sqlite3.connect(f"file:{self.path}?mode=ro",uri=True,timeout=self.timeout);connection.execute("SELECT 1").fetchone();return ComponentHealthDTO(self.component,HealthLevel.OK,"Base disponible",_now())
  except Exception:return ComponentHealthDTO(self.component,HealthLevel.ERROR,"Comprobación read-only fallida",_now())
  finally:
   if connection is not None:connection.close()

class ApplicationEventBusHealthProvider:
 component="application_event_bus"
 def __init__(self,bus,diagnostics):self.bus=bus;self.diagnostics=diagnostics
 def check(self):
  if self.bus is None or not self.bus.enabled:return ComponentHealthDTO(self.component,HealthLevel.DISABLED,"Bus deshabilitado",_now())
  items=self.diagnostics.snapshot() if self.diagnostics is not None else ();last=items[-1].timestamp.isoformat() if items else "N/D"
  return ComponentHealthDTO(self.component,HealthLevel.OK,f"Suscriptores {self.bus.subscriber_count()}; diagnósticos {len(items)}; último {last}",_now())

class SecurityHealthProvider:
 component="security"
 def __init__(self,enabled,sessions,*,utcnow=lambda:datetime.now(timezone.utc)):self.enabled=enabled;self.sessions=sessions;self.utcnow=utcnow
 def check(self):
  if not self.enabled:return ComponentHealthDTO(self.component,HealthLevel.DISABLED,"Seguridad deshabilitada explícitamente",_now())
  session=self.sessions.current()
  if session is None:return ComponentHealthDTO(self.component,HealthLevel.WARNING,"Sin sesión autenticada",_now())
  elapsed=(self.utcnow()-session.last_activity_at).total_seconds();remaining=max(0,self.sessions.idle_timeout_seconds-elapsed)
  return ComponentHealthDTO(self.component,HealthLevel.OK,f"Sesión autenticada; rol {session.role.value}; timeout {remaining:.0f}s",_now())

class BackupHealthProvider:
 component="backup"
 def __init__(self,enabled,maintenance,history=lambda:()):self.enabled=enabled;self.maintenance=maintenance;self.history=history
 def check(self):
  if not self.enabled:return ComponentHealthDTO(self.component,HealthLevel.DISABLED,"Backup deshabilitado",_now())
  state=self.maintenance.state.value;items=self.history();last=items[-1] if items else None
  if state=="FAILED":level=HealthLevel.ERROR
  elif state in {"RESTORING","QUIESCING","BACKUP_IN_PROGRESS"}:level=HealthLevel.WARNING
  else:level=HealthLevel.OK
  detail=("; última operación correcta" if last and last.success else "; última operación fallida" if last else "")
  return ComponentHealthDTO(self.component,level,f"Estado {state}{detail}",_now())

class StaticComponentHealthProvider:
 def __init__(self,component,*,enabled,initialized=None):self.component=component;self.enabled=enabled;self.initialized=initialized
 def check(self):
  if not self.enabled:return ComponentHealthDTO(self.component,HealthLevel.DISABLED,"Módulo deshabilitado",_now())
  if self.initialized is True:return ComponentHealthDTO(self.component,HealthLevel.OK,"Módulo inicializado",_now())
  if self.initialized is False:return ComponentHealthDTO(self.component,HealthLevel.ERROR,"Módulo no inicializado",_now())
  return ComponentHealthDTO(self.component,HealthLevel.UNKNOWN,"Inicialización desconocida",_now())
