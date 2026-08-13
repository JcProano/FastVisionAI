"""Thread-safe configuration lifecycle without runtime reconstruction."""
from __future__ import annotations
import json,os,shutil,tempfile,threading
from datetime import datetime,timezone
from pathlib import Path
from .contracts import *
from .diff import configuration_diff
from .validators import redact
from .validators import known_only
from src.version import __version__
class ConfigurationService:
 def __init__(self,loader,path:Path,profile:ConfigurationProfile,*,backup_count=10,audit_callback=None,application_version=__version__):
  if backup_count<=0:raise ValueError("backup_count must be positive")
  self.loader=loader;self.path=path;self.profile=profile;self.backup_count=backup_count;self.audit=audit_callback;self.application_version=application_version;self._lock=threading.RLock();self._current=loader.load(path,profile);self.restart_required_pending=False
 def current(self):
  with self._lock:return self._current
 def validate_candidate(self,candidate):
  result=self.loader.validator.validate(candidate,self.profile);self._audit("CONFIG_VALIDATED");return result
 def diff(self,candidate):return configuration_diff(self.current().as_mapping(),candidate)
 def reload(self):
  previous=self.current();loaded=self.loader.load(self.path,self.profile);difference=configuration_diff(previous.as_mapping(),loaded.as_mapping())
  with self._lock:self._current=loaded;self.restart_required_pending=bool(difference.restart_required or difference.immutable)
  self._audit("CONFIG_RELOADED");return ConfigurationOperationResult(True,"Snapshot recargado; los servicios no fueron reconstruidos.",diff=difference)
 def save(self,candidate):
  validation=self.loader.validator.validate(candidate,self.profile)
  if not validation.valid:return ConfigurationOperationResult(False,"Configuración inválida; no se guardó.",validation)
  candidate=known_only(candidate);difference=self.diff(candidate);directory=self.path.parent;directory.mkdir(parents=True,exist_ok=True);descriptor,name=tempfile.mkstemp(prefix=f".{self.path.name}.",suffix=".tmp",dir=directory);temporary=Path(name);warning=None
  try:
   with os.fdopen(descriptor,"w",encoding="utf-8") as stream:json.dump(candidate,stream,indent=2,sort_keys=True);stream.write("\n");stream.flush();os.fsync(stream.fileno())
   self.loader.load(temporary,self.profile)
   backups=directory/"backups";backups.mkdir(parents=True,exist_ok=True)
   stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ");backup=backups/f"{self.path.stem}.{stamp}.json"
   if self.path.exists():shutil.copyfile(self.path,backup)
   os.replace(temporary,self.path)
   try:self._fsync_directory(directory)
   except Exception:warning="La configuración se guardó, pero no se pudo confirmar la sincronización del directorio."
   loaded=self.loader.load(self.path,self.profile)
   with self._lock:self._current=loaded;self.restart_required_pending=bool(difference.restart_required or difference.immutable)
   try:self._rotate(backups)
   except Exception:warning="La configuración se guardó, pero no se pudieron rotar todas las copias antiguas."
   self._audit("CONFIG_SAVED");return ConfigurationOperationResult(True,"Configuración guardada; los cambios no se aplicaron automáticamente.",validation,difference,warning)
  except Exception as exc:temporary.unlink(missing_ok=True);return ConfigurationOperationResult(False,"No se pudo guardar; el archivo original permanece disponible.",validation,difference)
 def import_candidate(self,path:Path):
  try:snapshot=self.loader.load(path,self.profile);candidate=snapshot.as_mapping();return candidate,self.diff(candidate)
  except Exception:self._audit("CONFIG_IMPORT_REJECTED");raise
 def export(self,path:Path,*,overwrite=False):
  if path.exists() and not overwrite:raise ConfigurationError("El destino de exportación ya existe.")
  value=redact(self.current().as_mapping());value["exported_at"]=datetime.now(timezone.utc).isoformat();value["exported_by_version"]=self.application_version
  path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,indent=2,sort_keys=True)+"\n",encoding="utf-8");return ConfigurationOperationResult(True,"Configuración exportada sin secretos.")
 def _rotate(self,directory):
  items=sorted(directory.glob(f"{self.path.stem}.*.json"),key=lambda p:p.name,reverse=True)
  for item in items[self.backup_count:]:item.unlink()
 @staticmethod
 def _fsync_directory(directory):
  descriptor=os.open(directory,os.O_RDONLY)
  try:os.fsync(descriptor)
  finally:os.close(descriptor)
 def _audit(self,event):
  if self.audit:
   try:self.audit(event,{"profile":self.profile.value})
   except Exception:pass
