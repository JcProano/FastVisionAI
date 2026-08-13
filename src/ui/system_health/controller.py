from src.core.security import AuthorizationPermission
from .contracts import SystemHealthPresentationDTO
class SystemHealthController:
 def __init__(self,service,authorization=None,*,security_disabled=False,audit_callback=None):self.service=service;self.authorization=authorization;self.security_disabled=security_disabled;self.audit_callback=audit_callback
 def require(self):
  if self.security_disabled:return True
  if self.authorization is None or not self.authorization.require(AuthorizationPermission.VIEW_SYSTEM_HEALTH).allowed:raise PermissionError("operation is not authorized")
  return True
 def snapshot(self):
  self.require();health=self.service.snapshot();performance=self.service.performance_snapshot()
  def value(number,suffix=""):return "N/D" if number is None else f"{number:.1f}{suffix}"
  seconds=int(health.uptime_seconds);uptime=f"{seconds//3600:02d}:{seconds%3600//60:02d}:{seconds%60:02d}"
  return SystemHealthPresentationDTO(health.overall_level.value,tuple((item.component,item.level.value,item.message,item.checked_at.isoformat()) for item in health.components),value(performance.fps),value(performance.frame_interval_ms," ms"),value(performance.processing_latency_ms," ms"),value(performance.inference_latency_ms," ms"),"N/D" if performance.queue_depth is None else str(performance.queue_depth),"N/D" if performance.dropped_frames is None else str(performance.dropped_frames),value(performance.memory_usage_mb," MB"),uptime)
 def record_viewed(self):
  self.require()
  if self.audit_callback:
   try:self.audit_callback("SYSTEM_HEALTH_VIEWED",{})
   except Exception:pass
