from __future__ import annotations
from typing import Any
from .contracts import *
from .validators import redact
HOT={"dashboard.metrics_refresh_ms","dashboard.event_debounce_seconds","dashboard.history_limit","reports.dashboard_refresh_seconds","people_search.debounce_ms","people_search.default_page_size","system_health.dashboard_refresh_seconds","identification_popup.registered_cooldown_seconds","identification_popup.unknown_cooldown_seconds","identification_popup.unknown_popup_timeout_seconds"}
IMMUTABLE={"config_schema_version","profile_name","profile_version","configuration_manager.enabled","configuration_manager.profile"}
def configuration_diff(old:dict,new:dict)->ConfigurationDiffDTO:
 flat_old=_flatten(old);flat_new=_flatten(new);changes=[]
 for path in sorted(set(flat_old)|set(flat_new)):
  before=flat_old.get(path);after=flat_new.get(path)
  if before==after:continue
  section,_,field=path.partition(".");impact=ConfigurationImpact.IMMUTABLE_AT_RUNTIME if path in IMMUTABLE else ConfigurationImpact.HOT_RELOADABLE if path in HOT else ConfigurationImpact.RESTART_REQUIRED
  changes.append(ConfigurationChangeDTO(section,field,redact(before,path),redact(after,path),impact))
 return ConfigurationDiffDTO(tuple(changes))
def _flatten(value:Any,prefix=""):
 result={}
 if isinstance(value,dict):
  for key,item in value.items():result.update(_flatten(item,f"{prefix}.{key}" if prefix else str(key)))
 elif isinstance(value,(list,tuple)):result[prefix]=tuple(value)
 else:result[prefix]=value
 return result
