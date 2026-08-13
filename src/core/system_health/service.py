"""Read-only health aggregation with provider failure isolation."""
from __future__ import annotations
import logging,threading,time
from datetime import datetime,timezone
from .contracts import ComponentHealthDTO,HealthLevel,SystemHealthDTO
LOGGER=logging.getLogger(__name__)
class SystemHealthService:
 def __init__(self,providers=(),metrics=None,*,monotonic=time.monotonic,utcnow=lambda:datetime.now(timezone.utc)):
  self._providers=list(providers);self.metrics=metrics;self._monotonic=monotonic;self._utcnow=utcnow;self._started=monotonic();self._lock=threading.RLock()
 def snapshot(self):
  with self._lock:providers=tuple(self._providers)
  components=[]
  for provider in providers:
   try:components.append(provider.check())
   except Exception as exc:
    LOGGER.warning("System health provider failed safely; component=%s exception_type=%s",getattr(provider,"component","unknown"),type(exc).__name__);components.append(ComponentHealthDTO(str(getattr(provider,"component","unknown")),HealthLevel.ERROR,"Comprobación de salud fallida",self._utcnow()))
  return SystemHealthDTO(overall_level(tuple(components)),tuple(components),max(0,self._monotonic()-self._started),self._utcnow())
 def performance_snapshot(self):return self.metrics.snapshot()
 def observe_frame(self,timestamp=None):self.metrics.observe_frame(timestamp)
 def observe_counters(self,**kwargs):self.metrics.observe_counters(**kwargs)
def overall_level(components):
 active=[item.level for item in components if item.level is not HealthLevel.DISABLED]
 if not active:return HealthLevel.UNKNOWN
 for level in (HealthLevel.ERROR,HealthLevel.WARNING,HealthLevel.UNKNOWN,HealthLevel.OK):
  if level in active:return level
 return HealthLevel.UNKNOWN
